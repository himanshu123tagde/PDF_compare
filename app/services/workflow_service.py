import logging
import uuid

from app.config import settings
from app.services.batch_service import BatchScraperService
from app.services.scraper_service import ScraperService, utcnow_iso
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(self, batch_service: BatchScraperService, scraper_service: ScraperService):
        self.batch_service = batch_service
        self.scraper = scraper_service
        self.storage = StorageService()

    def create_workflow(
        self,
        product_name: str,
        gov_urls: list[str],
        description: str | None = None,
    ) -> dict:
        normalized = self._normalize_urls(gov_urls)

        if len(normalized) < settings.WORKFLOW_MIN_URLS:
            raise ValueError(
                f"At least {settings.WORKFLOW_MIN_URLS} government URLs are required."
            )
        if len(normalized) > settings.WORKFLOW_MAX_URLS:
            raise ValueError(
                f"Maximum {settings.WORKFLOW_MAX_URLS} government URLs allowed per workflow."
            )

        batch_job = self.batch_service.create_job(normalized)

        workflow_id = str(uuid.uuid4())
        now = utcnow_iso()

        workflow = {
            "id": workflow_id,
            "product_name": product_name.strip(),
            "description": description.strip() if description else None,
            "status": "scraping",
            "gov_urls": normalized,
            "gov_article_ids": [],
            "batch_job_id": batch_job["id"],
            "company_document_id": None,
            "comparison_id": None,
            "report_id": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }

        self.storage.save_workflow(workflow_id, workflow)
        logger.info("Created workflow %s for product '%s'", workflow_id, product_name)
        return workflow

    def list_workflows(self) -> list[dict]:
        workflows = self.storage.list_workflows()
        return [self._sync_scrape_status(workflow) for workflow in workflows]

    def get_workflow(self, workflow_id: str) -> dict | None:
        workflow = self.storage.load_workflow(workflow_id)
        if not workflow:
            return None
        return self._sync_scrape_status(workflow)

    def get_gov_data(self, workflow_id: str) -> dict | None:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return None

        articles = []
        for article_id in workflow.get("gov_article_ids", []):
            article = self.scraper.get_article(article_id)
            if not article:
                continue
            articles.append({
                "id": article["id"],
                "url": article["url"],
                "status": article["status"],
                "extracted_title": article.get("extracted_title"),
                "cleaned_text": article.get("cleaned_text"),
                "admin_edited_text": article.get("admin_edited_text"),
                "word_count": article.get("word_count", 0),
                "error_message": article.get("error_message"),
            })

        return {
            "workflow_id": workflow["id"],
            "product_name": workflow["product_name"],
            "status": workflow["status"],
            "articles": articles,
        }

    def attach_company_document(self, workflow_id: str, document_id: str) -> dict | None:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return None
        if workflow["status"] == "failed":
            raise ValueError("Cannot attach a document to a failed workflow.")

        workflow["company_document_id"] = document_id
        if workflow["status"] == "completed":
            workflow["status"] = "ready"
            workflow["comparison_id"] = None
            workflow["report_id"] = None
        workflow["updated_at"] = utcnow_iso()
        self.storage.save_workflow(workflow_id, workflow)
        return workflow

    def _normalize_urls(self, urls: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            normalized = url.strip().rstrip("/")
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def _sync_scrape_status(self, workflow: dict) -> dict:
        if workflow["status"] != "scraping":
            return workflow

        batch_job = self.storage.load_batch_job(workflow["batch_job_id"])
        if not batch_job:
            workflow["status"] = "failed"
            workflow["error_message"] = "Batch scrape job not found."
            workflow["updated_at"] = utcnow_iso()
            self.storage.save_workflow(workflow["id"], workflow)
            return workflow

        if batch_job["status"] in ("queued", "running"):
            return workflow

        article_ids: list[str] = []
        failed_urls: list[str] = []

        for item in batch_job["items"]:
            if item["status"] == "success" and item.get("article_id"):
                article_ids.append(item["article_id"])
            elif item["status"] == "failed":
                failed_urls.append(item["url"])

        workflow["gov_article_ids"] = article_ids
        workflow["updated_at"] = utcnow_iso()

        if failed_urls or len(article_ids) < len(workflow["gov_urls"]):
            workflow["status"] = "failed"
            workflow["error_message"] = (
                f"{len(failed_urls)} of {len(workflow['gov_urls'])} "
                "government URL(s) failed to scrape."
            )
        else:
            workflow["status"] = "ready"
            workflow["error_message"] = None

        self.storage.save_workflow(workflow["id"], workflow)
        return workflow
