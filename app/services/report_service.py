import json
import logging
import re
import uuid

from app.config import settings
from app.prompts.fixed_document_prompts import (
    build_fixed_document_prompt,
    load_fixed_document_system_prompt,
)
from app.services.epa_document_context import collect_epa_document_context, collect_gov_sources_from_workflow
from app.services.fixed_document_renderer import (
    render_fixed_document_fallback,
    render_fixed_document_html,
)
from app.services.fixed_document_sections import (
    inject_mandatory_sections,
    inject_preserved_images,
    render_hazard_classifications_section,
)
from app.services.document_image_service import DocumentImageService
from app.services.openrouter_client import OpenRouterClient, OpenRouterError
from app.services.scraper_service import ScraperService, utcnow_iso
from app.services.sds_ecp_renderer import (
    apply_ecp_sds_layout,
    extract_epa_product_codes,
    extract_product_fields,
)
from app.services.sds_structure_extractor import ensure_sds_profile
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class ReportService:
    def __init__(self, openrouter_client: OpenRouterClient | None = None):
        self.storage = StorageService()
        self.openrouter = openrouter_client or OpenRouterClient()
        self.scraper = ScraperService()
        self.image_service = DocumentImageService(self.storage)

    async def generate_report(
        self,
        workflow: dict,
        comparison: dict,
        company_doc: dict,
    ) -> dict:
        structured = comparison.get("structured_result") or {}
        report_id = str(uuid.uuid4())
        now = utcnow_iso()

        html = await self._build_fixed_document_html(
            workflow,
            company_doc,
            structured,
            created_at=now,
        )
        html_path = self.storage.save_report_html(report_id, html)

        score = structured.get("overall_compliance_score")

        report = {
            "id": report_id,
            "workflow_id": workflow["id"],
            "comparison_id": comparison["id"],
            "product_name": workflow["product_name"],
            "summary": structured.get("executive_summary", ""),
            "assessment_confidence": structured.get("assessment_confidence", "low"),
            "compliance_score": score,
            "compliance_level": structured.get("compliance_level", "undetermined"),
            "missing_evidence": structured.get("missing_evidence") or [],
            "structured_result": structured,
            "html_type": "fixed_document",
            "html": html,
            "html_path": html_path,
            "created_at": now,
        }

        self.storage.save_report(report_id, report)
        logger.info("Generated fixed document HTML %s for workflow %s", report_id, workflow["id"])
        return report

    def get_report(self, report_id: str) -> dict | None:
        return self.storage.load_report(report_id)

    def get_report_html(
        self,
        report: dict,
        workflow: dict,
        *,
        company_doc: dict | None = None,
    ) -> str:
        if report.get("html") and report.get("html_type") == "fixed_document":
            return report["html"]

        structured = report.get("structured_result") or {}
        company_text = (company_doc or {}).get("extracted_text") or ""
        html = render_fixed_document_fallback(
            workflow,
            company_text=company_text,
            comparison_result=structured,
            created_at=report.get("created_at", ""),
        )
        report["html"] = html
        report["html_type"] = "fixed_document"
        report["html_path"] = self.storage.save_report_html(report["id"], html)
        self.storage.save_report(report["id"], report)
        return html

    async def _build_fixed_document_html(
        self,
        workflow: dict,
        company_doc: dict,
        comparison_result: dict,
        *,
        created_at: str,
    ) -> str:
        company_text = company_doc.get("extracted_text") or ""
        sds_profile = company_doc.get("sds_profile") or ensure_sds_profile(
            company_text, company_doc.get("filename", "")
        )
        gov_sources = collect_gov_sources_from_workflow(workflow, self.scraper)
        epa_context = collect_epa_document_context(gov_sources)
        try:
            body_html, document_title = await self._generate_fixed_document_body(
                workflow,
                company_doc,
                comparison_result,
                epa_context=epa_context,
            )
            body_html = self._apply_mandatory_epa_sections(
                body_html, epa_context, sds_profile=sds_profile
            )
            preserved_images = self.image_service.load_images_for_document(company_doc)
            is_sds = bool(sds_profile and sds_profile.get("is_sds"))
            body_html = inject_preserved_images(
                body_html,
                preserved_images,
                append_missing=not is_sds,
                exclude_roles=(
                    self.image_service.sds_managed_image_roles() if is_sds else None
                ),
            )
            if is_sds:
                epa_text = " ".join(
                    (s.get("text") or "") for s in gov_sources
                )
                hazard = (epa_context or {}).get("hazard_classifications") or {}
                product_fields = extract_product_fields(
                    company_text,
                    workflow["product_name"],
                )
                product_fields.update(extract_epa_product_codes(epa_text))
                logo_html = self.image_service.render_ecp_brand_logo_html()
                body_html = apply_ecp_sds_layout(
                    body_html,
                    product_fields=product_fields,
                    images=preserved_images,
                    epa_hazard_text=hazard.get("raw_text") or "",
                    comparison_result=comparison_result,
                    logo_html=logo_html,
                )
            if not document_title and sds_profile.get("is_sds"):
                document_title = f"Safety Data Sheet — {workflow['product_name']}"
            return render_fixed_document_html(
                workflow,
                document_title=document_title,
                body_html=body_html,
                created_at=created_at,
                sds_profile=sds_profile,
            )
        except (OpenRouterError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "AI fixed document generation failed for workflow %s: %s",
                workflow.get("id"),
                exc,
            )
            preserved_images = self.image_service.load_images_for_document(company_doc)
            body = render_fixed_document_fallback(
                workflow,
                company_text=company_text,
                comparison_result=comparison_result,
                created_at=created_at,
                preserved_images=preserved_images,
                sds_profile=sds_profile,
                gov_sources=gov_sources,
                epa_context=epa_context,
            )
            return body

    async def _generate_fixed_document_body(
        self,
        workflow: dict,
        company_doc: dict,
        comparison_result: dict,
        *,
        epa_context: dict | None = None,
    ) -> tuple[str, str]:
        user_prompt = build_fixed_document_prompt(
            product_name=workflow["product_name"],
            description=workflow.get("description"),
            company_filename=company_doc["filename"],
            company_text=company_doc.get("extracted_text") or "",
            comparison_result=comparison_result,
            epa_context=epa_context,
            preserved_images=self.image_service.load_images_for_document(company_doc),
            sds_profile=company_doc.get("sds_profile") or ensure_sds_profile(
                company_doc.get("extracted_text") or "",
                company_doc.get("filename", ""),
            ),
        )
        messages = [
            {"role": "system", "content": load_fixed_document_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]

        last_error: Exception | None = None
        for attempt in range(2):
            response = await self.openrouter.chat_completion(messages)
            raw_content = self.openrouter.extract_message_content(response)

            try:
                parsed = self._parse_json_response(raw_content)
                body_html = (parsed.get("body_html") or "").strip()
                document_title = (parsed.get("document_title") or "").strip()
                if not body_html:
                    raise ValueError("AI response missing body_html.")
                default_title = f"{workflow['product_name']} — Safety Data Sheet"
                return body_html, document_title or default_title
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning("Fixed document JSON parse failed (attempt %s): %s", attempt + 1, exc)
                if attempt == 0:
                    messages.append({"role": "assistant", "content": raw_content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was not valid JSON or was missing body_html. "
                            "Return only a corrected JSON object matching the schema."
                        ),
                    })

        raise ValueError(f"AI returned invalid fixed document JSON: {last_error}")

    @staticmethod
    def _apply_mandatory_epa_sections(
        body_html: str,
        epa_context: dict | None,
        *,
        sds_profile: dict | None = None,
    ) -> str:
        if not epa_context:
            return body_html

        inline = bool(sds_profile and sds_profile.get("is_sds"))
        hazard_html = ""
        hazard = epa_context.get("hazard_classifications")
        if hazard:
            hazard_html = render_hazard_classifications_section(hazard, inline=inline)

        return inject_mandatory_sections(
            body_html,
            hazard_section_html=hazard_html,
            sds_profile=sds_profile,
        )

    @staticmethod
    def _parse_json_response(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object.")
        return parsed
