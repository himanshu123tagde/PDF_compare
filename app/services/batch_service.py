import asyncio
import logging
import uuid
from collections import defaultdict

from app.config import settings
from app.services.scraper_service import ScraperService, utcnow_iso
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class BatchScraperService:
    def __init__(self, scraper_service: ScraperService):
        self.scraper = scraper_service
        self.storage = StorageService()
        self._job_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._running_tasks: dict[str, asyncio.Task] = {}

    def _normalize_urls(self, urls: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            normalized = url.strip().rstrip("/")
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def _recompute_counts(self, job: dict) -> None:
        succeeded = failed = pending = running = 0
        for item in job["items"]:
            status = item["status"]
            if status == "success":
                succeeded += 1
            elif status == "failed":
                failed += 1
            elif status == "running":
                running += 1
            else:
                pending += 1

        job["succeeded"] = succeeded
        job["failed"] = failed
        job["pending"] = pending
        job["running"] = running
        job["completed"] = succeeded + failed

    def create_job(self, urls: list[str]) -> dict:
        normalized = self._normalize_urls(urls)

        if not normalized:
            raise ValueError("At least one valid URL is required.")
        if len(normalized) > settings.BATCH_MAX_URLS:
            raise ValueError(
                f"Maximum {settings.BATCH_MAX_URLS} URLs allowed per batch."
            )

        job_id = str(uuid.uuid4())
        now = utcnow_iso()

        job = {
            "id": job_id,
            "status": "queued",
            "total": len(normalized),
            "completed": 0,
            "succeeded": 0,
            "failed": 0,
            "pending": len(normalized),
            "running": 0,
            "items": [
                {
                    "url": url,
                    "status": "pending",
                    "article_id": None,
                    "error_message": None,
                }
                for url in normalized
            ],
            "created_at": now,
            "updated_at": now,
        }

        self.storage.save_batch_job(job_id, job)
        task = asyncio.create_task(self._run_job(job_id))
        self._running_tasks[job_id] = task
        task.add_done_callback(lambda _: self._running_tasks.pop(job_id, None))

        return job

    async def _update_item(
        self,
        job_id: str,
        index: int,
        *,
        status: str,
        article_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self._job_locks[job_id]:
            job = self.storage.load_batch_job(job_id)
            if not job:
                return

            item = job["items"][index]
            item["status"] = status
            if article_id is not None:
                item["article_id"] = article_id
            if error_message is not None:
                item["error_message"] = error_message

            self._recompute_counts(job)
            job["updated_at"] = utcnow_iso()
            self.storage.save_batch_job(job_id, job)

    async def _process_item(self, job_id: str, index: int, url: str) -> None:
        await self._update_item(job_id, index, status="running")

        try:
            article = await self.scraper.scrape_url(url)
            await self._update_item(
                job_id,
                index,
                status=article.get("status", "failed"),
                article_id=article.get("id"),
                error_message=article.get("error_message"),
            )
        except Exception as e:
            logger.error("Batch scrape failed for %s: %s", url, e)
            await self._update_item(
                job_id,
                index,
                status="failed",
                error_message=str(e),
            )

    async def _run_job(self, job_id: str) -> None:
        job = self.storage.load_batch_job(job_id)
        if not job:
            return

        async with self._job_locks[job_id]:
            job["status"] = "running"
            job["updated_at"] = utcnow_iso()
            self.storage.save_batch_job(job_id, job)

        tasks = [
            self._process_item(job_id, index, item["url"])
            for index, item in enumerate(job["items"])
        ]

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error("Batch job %s failed: %s", job_id, e)

        async with self._job_locks[job_id]:
            job = self.storage.load_batch_job(job_id)
            if not job:
                return

            self._recompute_counts(job)
            job["status"] = "completed"
            job["updated_at"] = utcnow_iso()
            self.storage.save_batch_job(job_id, job)

    def get_job(self, job_id: str) -> dict | None:
        return self.storage.load_batch_job(job_id)
