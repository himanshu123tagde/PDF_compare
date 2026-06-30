import html
import re
from datetime import datetime

from app.services.fixed_document_sections import inject_preserved_images
from app.services.sds_ecp_renderer import (
    apply_ecp_sds_layout,
    extract_epa_product_codes,
    extract_product_fields,
)
from app.services.document_image_service import DocumentImageService


def _e(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _fallback_body_from_company_text(company_text: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", company_text) if p.strip()]
    if not paragraphs:
        return "<p>No document content available.</p>"
    return "".join(f"<p>{_e(p)}</p>" for p in paragraphs)


def _append_gap_sections(body_html: str, comparison_result: dict) -> str:
    gaps = comparison_result.get("coverage_gaps") or comparison_result.get("critical_gaps") or []
    if not gaps:
        return body_html

    sections = ['<section class="revised"><h2>Compliance Additions</h2>']
    for gap in gaps:
        action = gap.get("recommended_action") or gap.get("description") or ""
        if not action:
            continue
        req_id = gap.get("gov_requirement_id", "")
        heading = f"Requirement {req_id}" if req_id else "Additional Requirement"
        sections.append(
            f"<div class='revised-block'>"
            f"<h3>{_e(heading)}</h3>"
            f"<p>{_e(action)}</p>"
            f"</div>"
        )
    sections.append("</section>")
    return body_html + "".join(sections)


def render_fixed_document_html(
    workflow: dict,
    *,
    document_title: str,
    body_html: str,
    created_at: str,
    sds_profile: dict | None = None,
) -> str:
    product = _e(workflow.get("product_name", "Product"))
    is_sds = bool(sds_profile and sds_profile.get("is_sds"))
    if is_sds and not document_title:
        document_title = f"Safety Data Sheet — {product}"
    title = _e(document_title or f"{product} — Safety Data Sheet")
    generated = _e(created_at or datetime.utcnow().isoformat())
    doc_class = "document sds-document ecp-sds" if is_sds else "document"
    doc_label = "SDS" if is_sds else "Document"

    header_html = ""
    footer_html = ""
    if not is_sds:
        header_html = f"""
    <header class="document-header">
      <h1>{title}</h1>
      <div class="document-meta">
        Product: {product} · {doc_label} · Revised: {generated}
      </div>
    </header>"""
        footer_html = """
    <footer class="document-footer">
      Compliance-revised SDS draft generated for internal review. Verify against official government sources before publication.
    </footer>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    :root {{
      --text: #111827;
      --muted: #4b5563;
      --border: #d1d5db;
      --revised-bg: #fffbeb;
      --revised-border: #f59e0b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Times New Roman", Georgia, serif;
      color: var(--text);
      line-height: 1.6;
      font-size: 12pt;
      background: #fff;
    }}
    .document {{
      max-width: 210mm;
      margin: 0 auto;
      padding: 20mm 18mm 24mm;
    }}
    .document-header {{
      border-bottom: 2px solid var(--border);
      margin-bottom: 24px;
      padding-bottom: 12px;
    }}
    .document-header h1 {{
      margin: 0 0 6px;
      font-size: 20pt;
      line-height: 1.25;
    }}
    .document-meta {{
      color: var(--muted);
      font-size: 10pt;
      font-family: "Segoe UI", Arial, sans-serif;
    }}
    .document-body h1, .document-body h2, .document-body h3 {{
      line-height: 1.3;
      margin: 1.2em 0 0.5em;
    }}
    .document-body h1 {{ font-size: 18pt; }}
    .document-body h2 {{ font-size: 14pt; }}
    .document-body h3 {{ font-size: 12pt; }}
    .document-body p {{ margin: 0 0 0.75em; }}
    .document-body ul, .document-body ol {{
      margin: 0 0 0.75em;
      padding-left: 1.4em;
    }}
    .document-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0 0 1em;
      font-size: 11pt;
    }}
    .document-body th, .document-body td {{
      border: 1px solid var(--border);
      padding: 8px 10px;
      vertical-align: top;
      text-align: left;
    }}
    .document-body th {{
      background: #f9fafb;
      font-weight: 700;
    }}
    .revised, .revised-block {{
      background: var(--revised-bg);
      border-left: 3px solid var(--revised-border);
      padding: 12px 14px;
      margin: 0 0 1em;
    }}
    .preserved-original-image {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 0.5em 0;
    }}
    .preserved-figure {{
      margin: 0 0 1em;
      text-align: left;
    }}
    .preserved-original-images {{
      margin-top: 1.5em;
    }}
    .sds-document .document-body {{
      font-family: Arial, Helvetica, "Segoe UI", sans-serif;
      font-size: 10pt;
      line-height: 1.45;
    }}
    .sds-document .sds-section {{
      margin: 0 0 1.25em;
      page-break-inside: avoid;
    }}
    .sds-document .sds-section-heading {{
      font-size: 11pt;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.02em;
      border-bottom: 1.5px solid #1f2937;
      padding-bottom: 4px;
      margin: 1em 0 0.6em;
    }}
    .sds-document .document-body table {{
      font-size: 9.5pt;
    }}
    .sds-document .document-body th {{
      background: #e5e7eb;
      font-weight: 700;
      text-transform: none;
    }}
    .ecp-sds .document-body {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 9.5pt;
      line-height: 1.35;
      color: #000;
    }}
    .ecp-sds .ecp-cover {{
      page-break-after: always;
      margin-bottom: 2em;
    }}
    .ecp-sds .ecp-cover-header {{
      text-align: center;
      margin-bottom: 1.5em;
    }}
    .ecp-sds .ecp-logo {{
      max-height: 72px;
      width: auto;
      margin: 0 auto 12px;
      display: block;
    }}
    .ecp-sds .ecp-title {{
      font-size: 16pt;
      font-weight: 700;
      margin: 0 0 8px;
      text-transform: none;
    }}
    .ecp-sds .ecp-dates {{
      font-size: 9pt;
      margin: 0;
    }}
    .ecp-sds .sds-section-heading {{
      font-size: 10pt;
      font-weight: 700;
      text-transform: uppercase;
      border-bottom: 1px solid #000;
      padding-bottom: 3px;
      margin: 1.2em 0 0.5em;
    }}
    .ecp-sds .ecp-info-table,
    .ecp-sds .ecp-product-table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0.5em 0 1em;
      font-size: 9pt;
    }}
    .ecp-sds .ecp-info-table th,
    .ecp-sds .ecp-info-table td,
    .ecp-sds .ecp-product-table th,
    .ecp-sds .ecp-product-table td {{
      border: 1px solid #333;
      padding: 4px 6px;
      vertical-align: top;
      text-align: left;
    }}
    .ecp-sds .ecp-info-table th {{
      width: 28%;
      background: #f3f4f6;
      font-weight: 700;
    }}
    .ecp-sds .ecp-product-table th {{
      background: #e5e7eb;
      font-weight: 700;
      font-size: 8.5pt;
    }}
    .ecp-sds .hazard-pictograms {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0.5em 0 1em;
    }}
    .ecp-sds .hazard-pictogram {{
      width: 72px;
      height: 72px;
      object-fit: contain;
      display: inline-block;
      margin: 0;
    }}
    .ecp-sds .ecp-disclaimer {{
      font-size: 8.5pt;
      text-align: justify;
    }}
    .ecp-sds .ecp-disclaimer-end {{
      font-size: 8pt;
      text-align: center;
      margin-top: 1em;
    }}
    .ecp-sds .epa-hazard-classifications table {{
      font-size: 9pt;
    }}
    .document-footer {{
      margin-top: 32px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 9pt;
      font-family: "Segoe UI", Arial, sans-serif;
    }}
    @media print {{
      body {{ background: #fff; }}
      .document {{
        max-width: none;
        margin: 0;
        padding: 0;
      }}
    }}
  </style>
</head>
<body>
  <article class="{doc_class}">
    {header_html}
    <div class="document-body">
      {body_html}
    </div>
    {footer_html}
  </article>
</body>
</html>"""


def render_fixed_document_fallback(
    workflow: dict,
    *,
    company_text: str,
    comparison_result: dict,
    created_at: str,
    preserved_images: list[dict] | None = None,
    sds_profile: dict | None = None,
    gov_sources: list[dict] | None = None,
    epa_context: dict | None = None,
) -> str:
    product = workflow.get("product_name", "Product")
    body = _fallback_body_from_company_text(company_text)
    body = _append_gap_sections(body, comparison_result)
    is_sds = bool(sds_profile and sds_profile.get("is_sds"))
    if preserved_images:
        body = inject_preserved_images(
            body,
            preserved_images,
            append_missing=not is_sds,
            exclude_roles=(
                DocumentImageService.sds_managed_image_roles() if is_sds else None
            ),
        )
    if is_sds:
        epa_text = " ".join((s.get("text") or "") for s in (gov_sources or []))
        hazard = (epa_context or {}).get("hazard_classifications") or {}
        product_fields = extract_product_fields(company_text, product)
        product_fields.update(extract_epa_product_codes(epa_text))
        logo_html = DocumentImageService.render_ecp_brand_logo_html()
        body = apply_ecp_sds_layout(
            body,
            product_fields=product_fields,
            images=preserved_images or [],
            epa_hazard_text=hazard.get("raw_text") or "",
            comparison_result=comparison_result,
            logo_html=logo_html,
        )
    title = f"Safety Data Sheet — {product}"
    if sds_profile and sds_profile.get("document_title"):
        title = f"{sds_profile['document_title']} — {product}"
    return render_fixed_document_html(
        workflow,
        document_title=title,
        body_html=body,
        created_at=created_at,
        sds_profile=sds_profile,
    )
