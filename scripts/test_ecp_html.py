import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.document_image_extractor import extract_images_from_pdf
from app.services.document_image_service import DocumentImageService, normalize_image_bytes
from app.services.fixed_document_renderer import render_fixed_document_html
from app.services.sds_ecp_renderer import apply_ecp_sds_layout, extract_product_fields


def to_data_url(ct: str, data: bytes) -> str:
    return f"data:{ct};base64,{base64.b64encode(data).decode()}"


def main() -> None:
    pdf_path = Path(r"C:\Users\himan\Downloads\input.pdf")
    raw = pdf_path.read_bytes()
    images = []
    for index, img in enumerate(extract_images_from_pdf(raw), start=1):
        norm, ct = normalize_image_bytes(img["data"], img["content_type"])
        images.append({
            "id": f"img-{index:03d}",
            "data_url": to_data_url(ct, norm),
            "role": img.get("role"),
            "page": img.get("page"),
        })

    body = """
<section class="sds-section" data-section="2">
<h2 class="sds-section-heading">2: HAZARDS IDENTIFICATION</h2>
<p>Test section 2 content.</p>
</section>
<section class="sds-section" data-section="13">
<h2 class="sds-section-heading">13: DISPOSAL CONSIDERATIONS</h2>
<p>Dispose in accordance with NZ regulations.</p>
</section>
"""
    fields = extract_product_fields(
        "CAS No. 67-56-1\nTrade name/designation: Methanol",
        "Methanol",
    )
    logo = DocumentImageService.render_ecp_brand_logo_html()
    body = apply_ecp_sds_layout(
        body,
        product_fields=fields,
        images=images,
        logo_html=logo,
    )
    html = render_fixed_document_html(
        {"product_name": "Methanol"},
        document_title="Safety Data Sheet",
        body_html=body,
        created_at="2026-06-29",
        sds_profile={"is_sds": True},
    )
    out = ROOT / "test_ecp_output.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")
    print("logo:", "ecp-logo" in html)
    print("pictograms:", html.count("hazard-pictogram"))
    print("disclaimer:", "Disclaimer" in html and "ECP Limited" in html)


if __name__ == "__main__":
    main()
