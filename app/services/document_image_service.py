import base64
import io
import logging
from functools import lru_cache
from pathlib import Path

from app.services.document_image_extractor import extract_images_from_bytes
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

_ECP_LOGO_PATH = Path(__file__).resolve().parent.parent / "icon" / "logo.jpg"
_SDS_MANAGED_IMAGE_ROLES = frozenset({"ecp_logo", "hazard_pictograms"})


def _image_id(index: int) -> str:
    return f"img-{index:03d}"


def _to_data_url(content_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def normalize_image_bytes(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Re-encode PDF image bytes so browsers can render them reliably."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                out = io.BytesIO()
                img.save(out, format="PNG")
                return out.getvalue(), "image/png"
            img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=92)
            return out.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.debug("Image normalize skipped (%s): %s", content_type, exc)
        return data, content_type


@lru_cache(maxsize=1)
def _load_ecp_brand_logo() -> tuple[bytes, str]:
    if not _ECP_LOGO_PATH.is_file():
        raise FileNotFoundError(f"ECP logo not found: {_ECP_LOGO_PATH}")
    data = _ECP_LOGO_PATH.read_bytes()
    normalized, content_type = normalize_image_bytes(data, "image/jpeg")
    return normalized, content_type


class DocumentImageService:
    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    def extract_and_store_images(
        self,
        document_id: str,
        file_bytes: bytes,
        extension: str,
    ) -> list[dict]:
        raw_images = extract_images_from_bytes(file_bytes, extension)
        stored: list[dict] = []

        for index, image in enumerate(raw_images, start=1):
            image_id = _image_id(index)
            normalized_data, content_type = normalize_image_bytes(
                image["data"],
                image["content_type"],
            )
            gridfs_id = self.storage.save_company_image(
                document_id,
                image_id,
                content_type,
                normalized_data,
            )
            entry = {
                "id": image_id,
                "content_type": content_type,
                "gridfs_id": gridfs_id,
                "source": image.get("source"),
                "role": image.get("role", "other"),
            }
            if image.get("page"):
                entry["page"] = image["page"]
            stored.append(entry)

        if stored:
            logger.info("Stored %s images for company document %s", len(stored), document_id)
        return stored

    def load_images_for_document(self, company_doc: dict) -> list[dict]:
        images: list[dict] = []
        for meta in company_doc.get("images") or []:
            image_id = meta.get("id")
            gridfs_id = meta.get("gridfs_id")
            content_type = meta.get("content_type", "image/png")
            if not image_id or not gridfs_id:
                continue
            data = self.storage.load_company_image(gridfs_id)
            if not data:
                continue
            normalized_data, normalized_type = normalize_image_bytes(data, content_type)
            role = meta.get("role")
            if not role or role == "other":
                page = meta.get("page")
                if page == 2:
                    role = "hazard_pictograms"
                else:
                    role = "other"
            images.append({
                "id": image_id,
                "content_type": normalized_type,
                "data_url": _to_data_url(normalized_type, normalized_data),
                "page": meta.get("page"),
                "source": meta.get("source"),
                "role": role,
            })
        return images

    @staticmethod
    def sds_managed_image_roles() -> frozenset[str]:
        return _SDS_MANAGED_IMAGE_ROLES

    @staticmethod
    def render_ecp_brand_logo_html() -> str:
        try:
            data, content_type = _load_ecp_brand_logo()
        except FileNotFoundError as exc:
            logger.warning("%s", exc)
            return ""
        data_url = _to_data_url(content_type, data)
        return (
            f'<img class="ecp-logo" src="{data_url}" alt="ECP Limited" />'
        )

    @staticmethod
    def hazard_pictogram_images(images: list[dict]) -> list[dict]:
        """Unique hazard pictograms from page 2 only."""
        seen_urls: set[str] = set()
        pictograms: list[dict] = []
        for image in images:
            if image.get("role") != "hazard_pictograms":
                continue
            if image.get("page") not in (None, 2):
                continue
            data_url = image.get("data_url") or ""
            if not data_url or data_url in seen_urls:
                continue
            seen_urls.add(data_url)
            pictograms.append(image)
        return pictograms
