import io
import logging

logger = logging.getLogger(__name__)


def extract_images_from_docx(file_bytes: bytes) -> list[dict]:
    try:
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        images: list[dict] = []
        seen_hashes: set[int] = set()

        for rel in doc.part.rels.values():
            if "image" not in rel.reltype:
                continue
            part = rel.target_part
            blob = part.blob
            blob_hash = hash(blob)
            if blob_hash in seen_hashes:
                continue
            seen_hashes.add(blob_hash)
            images.append({
                "content_type": getattr(part, "content_type", "image/png"),
                "data": blob,
                "source": "docx",
            })
        return images
    except Exception as exc:
        logger.warning("DOCX image extraction failed: %s", exc)
        return []


def _pdf_image_content_type(filter_name) -> str:
    if filter_name == "/DCTDecode":
        return "image/jpeg"
    if filter_name == "/JPXDecode":
        return "image/jp2"
    if filter_name == "/CCITTFaxDecode":
        return "image/tiff"
    return "image/png"


def _flate_rgb_to_png(data: bytes, width: int, height: int) -> tuple[bytes, str]:
    from PIL import Image

    expected = width * height * 3
    if len(data) < expected:
        raise ValueError(f"RGB stream too short: {len(data)} < {expected}")
    img = Image.frombytes("RGB", (width, height), data[:expected])
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), "image/png"


def _decode_pdf_image_data(obj) -> tuple[bytes, str] | None:
    try:
        data = obj.get_data()
    except Exception:
        return None
    if not data:
        return None

    filters = obj.get("/Filter")
    if isinstance(filters, list):
        filter_name = filters[-1]
    else:
        filter_name = filters

    if filter_name == "/DCTDecode":
        return data, "image/jpeg"

    width = int(obj.get("/Width", 0))
    height = int(obj.get("/Height", 0))
    color_space = obj.get("/ColorSpace")
    if isinstance(color_space, list):
        color_space = color_space[-1]
    if filter_name == "/FlateDecode" and color_space == "/DeviceRGB" and width and height:
        try:
            return _flate_rgb_to_png(data, width, height)
        except Exception as exc:
            logger.debug("FlateDecode RGB decode failed: %s", exc)

    return data, _pdf_image_content_type(filter_name)


def extract_images_from_pdf(file_bytes: bytes) -> list[dict]:
    try:
        from PyPDF2 import PdfReader
        from PyPDF2.generic import IndirectObject

        reader = PdfReader(io.BytesIO(file_bytes))
        images: list[dict] = []
        seen_hashes: set[int] = set()

        for page_index, page in enumerate(reader.pages):
            resources = page.get("/Resources")
            if not resources:
                continue
            if isinstance(resources, IndirectObject):
                resources = resources.get_object()
            xobjects = resources.get("/XObject")
            if not xobjects:
                continue
            if isinstance(xobjects, IndirectObject):
                xobjects = xobjects.get_object()

            for name in xobjects:
                obj = xobjects[name]
                if isinstance(obj, IndirectObject):
                    obj = obj.get_object()
                if obj.get("/Subtype") != "/Image":
                    continue
                decoded = _decode_pdf_image_data(obj)
                if not decoded:
                    continue
                data, content_type = decoded

                blob_hash = hash(data)
                if blob_hash in seen_hashes:
                    continue
                seen_hashes.add(blob_hash)

                page_num = page_index + 1
                role = "other"
                if page_num == 2 and content_type in ("image/png", "image/jpeg"):
                    # Section 2 GHS pictograms only (page 1 supplier logo is ignored).
                    role = "hazard_pictograms"
                elif content_type == "image/jpeg":
                    continue

                images.append({
                    "content_type": content_type,
                    "data": data,
                    "source": "pdf",
                    "page": page_num,
                    "role": role,
                })
        return images
    except Exception as exc:
        logger.warning("PDF image extraction failed: %s", exc)
        return []


def extract_images_from_bytes(file_bytes: bytes, extension: str) -> list[dict]:
    ext = extension.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if ext == ".docx":
        return extract_images_from_docx(file_bytes)
    if ext == ".pdf":
        return extract_images_from_pdf(file_bytes)
    return []
