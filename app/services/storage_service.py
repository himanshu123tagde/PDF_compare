from typing import Optional

from gridfs import GridFS

from app.config import settings
from app.database.mongo import get_app_collection, get_database, get_uploads_bucket_name


def _clean_document(document: dict | None) -> dict | None:
    if not document:
        return None
    cleaned = dict(document)
    cleaned.pop("_id", None)
    cleaned.pop("entity_type", None)
    return cleaned


class StorageService:
    ENTITY_ARTICLE = "article"
    ENTITY_BATCH_JOB = "batch_job"
    ENTITY_WORKFLOW = "workflow"
    ENTITY_COMPANY_DOCUMENT = "company_document"
    ENTITY_COMPARISON = "comparison"
    ENTITY_REPORT = "report"

    def __init__(self) -> None:
        self._collection = get_app_collection()
        self._gridfs = GridFS(get_database(), collection=get_uploads_bucket_name())
        self._collection_name = settings.MONGODB_COLLECTION_NAME

    def _upsert(self, entity_type: str, entity_id: str, data: dict) -> None:
        payload = dict(data)
        payload["entity_type"] = entity_type
        payload["id"] = entity_id
        self._collection.replace_one(
            {"entity_type": entity_type, "id": entity_id},
            payload,
            upsert=True,
        )

    def _find_one(self, entity_type: str, entity_id: str) -> Optional[dict]:
        return _clean_document(
            self._collection.find_one({"entity_type": entity_type, "id": entity_id})
        )

    def _find_many(self, entity_type: str) -> list[dict]:
        cursor = self._collection.find({"entity_type": entity_type}).sort("created_at", -1)
        return [_clean_document(doc) for doc in cursor if doc]

    def _mongo_ref(self, entity_type: str, entity_id: str, field: str = "") -> str:
        suffix = f"/{field}" if field else ""
        return f"mongo://{self._collection_name}/{entity_type}/{entity_id}{suffix}"

    def save_article(self, article_id: str, data: dict) -> None:
        self._upsert(self.ENTITY_ARTICLE, article_id, data)

    def load_article(self, article_id: str) -> Optional[dict]:
        return self._find_one(self.ENTITY_ARTICLE, article_id)

    def list_articles(self) -> list[dict]:
        return self._find_many(self.ENTITY_ARTICLE)

    def save_raw_html(self, article_id: str, html: str) -> str:
        reference = self._mongo_ref(self.ENTITY_ARTICLE, article_id, "raw_html")
        self._collection.update_one(
            {"entity_type": self.ENTITY_ARTICLE, "id": article_id},
            {"$set": {"raw_html": html, "raw_html_path": reference}},
            upsert=True,
        )
        return reference

    def update_article(self, article_id: str, updates: dict) -> Optional[dict]:
        article = self.load_article(article_id)
        if not article:
            return None
        article.update(updates)
        self.save_article(article_id, article)
        return article

    def save_batch_job(self, job_id: str, data: dict) -> None:
        self._upsert(self.ENTITY_BATCH_JOB, job_id, data)

    def load_batch_job(self, job_id: str) -> Optional[dict]:
        return self._find_one(self.ENTITY_BATCH_JOB, job_id)

    def save_workflow(self, workflow_id: str, data: dict) -> None:
        self._upsert(self.ENTITY_WORKFLOW, workflow_id, data)

    def load_workflow(self, workflow_id: str) -> Optional[dict]:
        return self._find_one(self.ENTITY_WORKFLOW, workflow_id)

    def list_workflows(self) -> list[dict]:
        return self._find_many(self.ENTITY_WORKFLOW)

    def save_company_document(self, document_id: str, data: dict) -> None:
        self._upsert(self.ENTITY_COMPANY_DOCUMENT, document_id, data)

    def load_company_document(self, document_id: str) -> Optional[dict]:
        document = self._find_one(self.ENTITY_COMPANY_DOCUMENT, document_id)
        if not document:
            return None
        document.pop("file_data", None)
        return document

    def save_upload_file(self, document_id: str, extension: str, file_bytes: bytes) -> str:
        file_id = self._gridfs.put(
            file_bytes,
            filename=f"{document_id}{extension}",
            metadata={"document_id": document_id, "extension": extension},
        )
        return f"mongo://{get_uploads_bucket_name()}/{file_id}"

    def save_company_image(
        self,
        document_id: str,
        image_id: str,
        content_type: str,
        file_bytes: bytes,
    ) -> str:
        file_id = self._gridfs.put(
            file_bytes,
            filename=f"{document_id}_{image_id}",
            metadata={
                "document_id": document_id,
                "image_id": image_id,
                "content_type": content_type,
                "kind": "company_image",
            },
        )
        return str(file_id)

    def load_company_image(self, gridfs_id: str) -> bytes | None:
        try:
            from bson import ObjectId

            return self._gridfs.get(ObjectId(gridfs_id)).read()
        except Exception:
            return None

    def save_comparison(self, comparison_id: str, data: dict) -> None:
        self._upsert(self.ENTITY_COMPARISON, comparison_id, data)

    def load_comparison(self, comparison_id: str) -> Optional[dict]:
        return self._find_one(self.ENTITY_COMPARISON, comparison_id)

    def save_report(self, report_id: str, data: dict) -> None:
        self._upsert(self.ENTITY_REPORT, report_id, data)

    def load_report(self, report_id: str) -> Optional[dict]:
        return self._find_one(self.ENTITY_REPORT, report_id)

    def save_report_html(self, report_id: str, html: str) -> str:
        reference = self._mongo_ref(self.ENTITY_REPORT, report_id, "html")
        self._collection.update_one(
            {"entity_type": self.ENTITY_REPORT, "id": report_id},
            {"$set": {"html": html, "html_path": reference}},
            upsert=True,
        )
        return reference
