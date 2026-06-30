import logging
import uuid

from app.config import settings
from app.services.document_image_service import DocumentImageService
from app.services.document_extractor import (
    detect_extension_from_filename,
    extract_text_from_bytes,
)
from app.services.sds_structure_extractor import ensure_sds_profile
from app.services.scraper_service import utcnow_iso
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class DocumentUploadService:
    def __init__(self):
        self.storage = StorageService()
        self.image_service = DocumentImageService(self.storage)
        self._allowed_extensions = {
            ext.strip().lower()
            for ext in settings.UPLOAD_ALLOWED_EXTENSIONS.split(",")
            if ext.strip()
        }
        self._max_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024

    def upload_company_document(
        self,
        workflow_id: str,
        filename: str,
        file_bytes: bytes,
    ) -> dict:
        if not filename or not filename.strip():
            raise ValueError("Filename is required.")

        if len(file_bytes) > self._max_bytes:
            raise ValueError(
                f"File exceeds maximum size of {settings.UPLOAD_MAX_SIZE_MB} MB."
            )

        extension = detect_extension_from_filename(filename)
        if not extension or extension not in self._allowed_extensions:
            allowed = ", ".join(sorted(self._allowed_extensions))
            raise ValueError(
                f"Unsupported file type. Allowed extensions: {allowed}"
            )

        document_id = str(uuid.uuid4())
        now = utcnow_iso()

        try:
            extracted_text = extract_text_from_bytes(file_bytes, extension)
            file_path = self.storage.save_upload_file(document_id, extension, file_bytes)
            images = self.image_service.extract_and_store_images(
                document_id, file_bytes, extension
            )
            sds_profile = ensure_sds_profile(extracted_text, filename.strip())
            word_count = len(extracted_text.split())

            document = {
                "id": document_id,
                "workflow_id": workflow_id,
                "filename": filename.strip(),
                "file_type": extension,
                "file_path": file_path,
                "extracted_text": extracted_text,
                "images": images,
                "sds_profile": sds_profile,
                "document_type": "sds",
                "word_count": word_count,
                "status": "processed",
                "error_message": None,
                "created_at": now,
            }
        except ValueError as e:
            document = {
                "id": document_id,
                "workflow_id": workflow_id,
                "filename": filename.strip(),
                "file_type": extension,
                "file_path": None,
                "extracted_text": None,
                "word_count": 0,
                "status": "failed",
                "error_message": str(e),
                "created_at": now,
            }

        self.storage.save_company_document(document_id, document)
        logger.info(
            "Uploaded company document %s for workflow %s (%s)",
            document_id,
            workflow_id,
            document["status"],
        )
        return document

    def get_company_document(self, document_id: str) -> dict | None:
        return self.storage.load_company_document(document_id)
