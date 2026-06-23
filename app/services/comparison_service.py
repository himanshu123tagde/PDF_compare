import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict

from app.config import settings
from app.prompts.compliance_prompts import build_user_prompt, load_system_prompt
from app.services.comparison_limiter import comparison_semaphore
from app.services.document_upload_service import DocumentUploadService
from app.services.openrouter_client import OpenRouterClient, OpenRouterError
from app.services.report_service import ReportService
from app.services.scraper_service import ScraperService, utcnow_iso
from app.services.storage_service import StorageService
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)


class ComparisonService:
    def __init__(
        self,
        workflow_service: WorkflowService,
        document_service: DocumentUploadService,
        scraper_service: ScraperService,
        report_service: ReportService,
        openrouter_client: OpenRouterClient | None = None,
    ):
        self.workflow_service = workflow_service
        self.document_service = document_service
        self.scraper = scraper_service
        self.report_service = report_service
        self.openrouter = openrouter_client or OpenRouterClient()
        self.storage = StorageService()
        self._job_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._running_tasks: dict[str, asyncio.Task] = {}

    def start_comparison(self, workflow_id: str) -> dict:
        workflow = self.workflow_service.get_workflow(workflow_id)
        if not workflow:
            raise ValueError("Workflow not found.")

        if workflow["status"] == "scraping":
            raise ValueError("Workflow is still scraping government sources.")
        if workflow["status"] == "failed":
            raise ValueError("Workflow has failed and cannot be compared.")
        if workflow["status"] == "comparing":
            comparison_id = workflow.get("comparison_id")
            if comparison_id:
                existing = self.storage.load_comparison(comparison_id)
                if existing and existing["status"] in ("queued", "running"):
                    return existing
            raise ValueError("A comparison is already in progress.")

        if not workflow.get("company_document_id"):
            raise ValueError("Upload a company document before running comparison.")

        company_doc = self.document_service.get_company_document(
            workflow["company_document_id"]
        )
        if not company_doc or company_doc["status"] != "processed":
            raise ValueError("Company document is missing or failed to process.")

        gov_sources = self._collect_gov_sources(workflow)
        if not gov_sources:
            raise ValueError("No government source text available for comparison.")

        comparison_id = str(uuid.uuid4())
        now = utcnow_iso()

        comparison = {
            "id": comparison_id,
            "workflow_id": workflow_id,
            "status": "queued",
            "model": settings.OPENROUTER_MODEL,
            "gov_sources": [
                {
                    "article_id": source["article_id"],
                    "url": source["url"],
                    "title": source.get("title"),
                }
                for source in gov_sources
            ],
            "company_document_id": company_doc["id"],
            "raw_ai_response": None,
            "structured_result": None,
            "token_usage": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }

        self.storage.save_comparison(comparison_id, comparison)
        self._set_workflow_status(
            workflow_id,
            status="comparing",
            comparison_id=comparison_id,
            report_id=None,
            error_message=None,
        )

        task = asyncio.create_task(self._run_comparison(comparison_id))
        self._running_tasks[comparison_id] = task
        task.add_done_callback(
            lambda _: self._running_tasks.pop(comparison_id, None)
        )

        return comparison

    def get_comparison(self, comparison_id: str) -> dict | None:
        return self.storage.load_comparison(comparison_id)

    def get_workflow_comparison(self, workflow_id: str) -> dict | None:
        workflow = self.workflow_service.get_workflow(workflow_id)
        if not workflow or not workflow.get("comparison_id"):
            return None
        return self.storage.load_comparison(workflow["comparison_id"])

    async def _run_comparison(self, comparison_id: str) -> None:
        async with comparison_semaphore:
            comparison = self.storage.load_comparison(comparison_id)
            if not comparison:
                return

            workflow_id = comparison["workflow_id"]
            await self._update_comparison(comparison_id, status="running")

            try:
                workflow = self.workflow_service.get_workflow(workflow_id)
                if not workflow:
                    raise ValueError("Workflow not found.")

                company_doc = self.document_service.get_company_document(
                    comparison["company_document_id"]
                )
                if not company_doc:
                    raise ValueError("Company document not found.")

                gov_sources = self._collect_gov_sources(workflow)
                user_prompt = build_user_prompt(
                    product_name=workflow["product_name"],
                    description=workflow.get("description"),
                    gov_sources=gov_sources,
                    company_filename=company_doc["filename"],
                    company_text=company_doc["extracted_text"] or "",
                )

                structured, raw_response, token_usage = await self._call_ai(user_prompt)

                await self._update_comparison(
                    comparison_id,
                    status="completed",
                    raw_ai_response=raw_response,
                    structured_result=structured,
                    token_usage=token_usage,
                    completed_at=utcnow_iso(),
                )

                comparison = self.storage.load_comparison(comparison_id)
                report = self.report_service.generate_report(workflow, comparison)

                self._set_workflow_status(
                    workflow_id,
                    status="completed",
                    comparison_id=comparison_id,
                    report_id=report["id"],
                    error_message=None,
                )

            except Exception as e:
                logger.error("Comparison %s failed: %s", comparison_id, e)
                await self._update_comparison(
                    comparison_id,
                    status="failed",
                    error_message=str(e),
                    completed_at=utcnow_iso(),
                )
                self._set_workflow_status(
                    workflow_id,
                    status="failed",
                    comparison_id=comparison_id,
                    error_message=str(e),
                )

    async def _call_ai(self, user_prompt: str) -> tuple[dict, str, dict]:
        messages = [
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]

        last_error: Exception | None = None
        for attempt in range(2):
            response = await self.openrouter.chat_completion(messages)
            raw_content = self.openrouter.extract_message_content(response)
            token_usage = self.openrouter.extract_token_usage(response)

            try:
                structured = self._parse_json_response(raw_content)
                self._validate_structured_result(structured)
                structured = self._sanitize_comparison_result(structured)
                return structured, raw_content, token_usage
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning("AI JSON parse failed (attempt %s): %s", attempt + 1, exc)
                if attempt == 0:
                    messages.append({"role": "assistant", "content": raw_content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was not valid JSON. "
                            "Return only a corrected JSON object matching the schema. "
                            "No markdown fences or extra text."
                        ),
                    })

        raise ValueError(f"AI returned invalid JSON: {last_error}")

    def _collect_gov_sources(self, workflow: dict) -> list[dict]:
        sources: list[dict] = []
        for article_id in workflow.get("gov_article_ids", []):
            article = self.scraper.get_article(article_id)
            if not article:
                continue

            text = (
                article.get("admin_edited_text")
                or article.get("cleaned_text")
                or article.get("extracted_text")
                or ""
            ).strip()

            if not text:
                continue

            sources.append({
                "article_id": article_id,
                "url": article["url"],
                "title": article.get("extracted_title"),
                "text": text,
            })
        return sources

    def _parse_json_response(self, content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object.")
        return parsed

    def _validate_structured_result(self, result: dict) -> None:
        required_keys = [
            "executive_summary",
            "assessment_confidence",
            "compliance_level",
            "gov_requirements",
            "alignments",
            "missing_evidence",
            "conflicts",
            "recommendations",
            "limitations",
        ]
        missing = [key for key in required_keys if key not in result]
        if missing:
            raise ValueError(f"AI response missing keys: {', '.join(missing)}")

        if not result.get("coverage_gaps") and not result.get("critical_gaps"):
            raise ValueError("AI response missing coverage_gaps.")

        allowed_confidence = {"high", "medium", "low"}
        if result.get("assessment_confidence") not in allowed_confidence:
            raise ValueError("Invalid assessment_confidence value.")

        allowed_levels = {"compliant", "partial", "non_compliant", "undetermined"}
        if result.get("compliance_level") not in allowed_levels:
            raise ValueError("Invalid compliance_level value.")

    def _sanitize_comparison_result(self, result: dict) -> dict:
        if not result.get("coverage_gaps") and result.get("critical_gaps"):
            result["coverage_gaps"] = result["critical_gaps"]

        gov_reqs = result.get("gov_requirements") or []
        detailed_count = sum(
            1 for item in gov_reqs if item.get("evidence_depth") == "detailed_obligation"
        )
        shallow_count = sum(
            1 for item in gov_reqs
            if item.get("evidence_depth") in ("regulatory_reference", "metadata_only")
        )
        confidence = result.get("assessment_confidence", "low")

        score = result.get("overall_compliance_score")
        if confidence != "high" or detailed_count < 3:
            result["overall_compliance_score"] = None
        elif score is not None:
            try:
                score_int = int(score)
                result["overall_compliance_score"] = max(0, min(100, score_int))
            except (TypeError, ValueError):
                result["overall_compliance_score"] = None

        if confidence == "low" or (shallow_count > 0 and detailed_count == 0):
            if result.get("compliance_level") == "non_compliant":
                result["compliance_level"] = "undetermined"
            result["overall_compliance_score"] = None

        verified_conflicts: list[dict] = []
        for conflict in result.get("conflicts") or []:
            gov_excerpt = (conflict.get("government_excerpt") or "").strip()
            company_excerpt = (conflict.get("company_excerpt") or "").strip()
            if gov_excerpt and company_excerpt:
                verified_conflicts.append(conflict)
        result["conflicts"] = verified_conflicts

        if result.get("compliance_level") == "non_compliant" and not verified_conflicts:
            has_confirmed_missing = any(
                item.get("status") == "missing"
                for item in (result.get("alignments") or [])
            )
            if not has_confirmed_missing:
                result["compliance_level"] = "undetermined"

        if result.get("missing_evidence") is None:
            result["missing_evidence"] = []

        return result

    async def _update_comparison(self, comparison_id: str, **updates) -> None:
        async with self._job_locks[comparison_id]:
            comparison = self.storage.load_comparison(comparison_id)
            if not comparison:
                return
            comparison.update(updates)
            comparison["updated_at"] = utcnow_iso()
            self.storage.save_comparison(comparison_id, comparison)

    def _set_workflow_status(
        self,
        workflow_id: str,
        *,
        status: str,
        comparison_id: str | None = None,
        report_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        workflow = self.storage.load_workflow(workflow_id)
        if not workflow:
            return

        workflow["status"] = status
        if comparison_id is not None:
            workflow["comparison_id"] = comparison_id
        if report_id is not None:
            workflow["report_id"] = report_id
        workflow["error_message"] = error_message
        workflow["updated_at"] = utcnow_iso()
        self.storage.save_workflow(workflow_id, workflow)
