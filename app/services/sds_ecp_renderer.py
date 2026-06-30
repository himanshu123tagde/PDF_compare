import html
import re
from datetime import datetime, timedelta

from app.data.ecp_sds_defaults import (
    ECP_DISCLAIMER,
    ECP_DISCLAIMER_END_MARKER,
    ECP_DISTRIBUTOR,
    SECTION_15_ACUTE_TOXIC_HANDLER,
    SECTION_15_DEFAULT_HANDLER,
)


def _e(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _issue_expiry_dates() -> tuple[str, str]:
    today = datetime.utcnow().date()
    issue = today.strftime("%d.%m.%Y")
    expiry = (today + timedelta(days=5 * 365)).strftime("%d.%m.%Y")
    return issue, expiry


def detect_acute_toxicity_category_1_or_2(
    *,
    epa_hazard_text: str = "",
    body_html: str = "",
    comparison_result: dict | None = None,
) -> bool:
    """True if acute toxicity GHS category 1 or 2 is indicated."""
    blobs = [epa_hazard_text, body_html]
    if comparison_result:
        for req in comparison_result.get("gov_requirements") or []:
            blobs.append(req.get("requirement_text") or "")
            blobs.append(req.get("source_excerpt") or "")

    combined = " ".join(blobs).lower()
    patterns = [
        r"acute\s+toxicity[^.\n]{0,80}category\s*[12]\b",
        r"acute\s+toxicity,\s*category\s*[12]\b",
        r"acute\s+toxic[^.\n]{0,40}category\s*[12]\b",
        r"\bacute\s+toxicity\b[^.\n]*\b(cat\.?\s*[12]|category\s*[12])\b",
    ]
    return any(re.search(p, combined, re.IGNORECASE) for p in patterns)


def extract_product_fields(company_text: str, product_name: str) -> dict:
    text = company_text or ""
    cas = ""
    cas_match = re.search(r"CAS\s*(?:No\.?|#)?\s*[:\s]*(\d{2,7}-\d{2}-\d)", text, re.I)
    if cas_match:
        cas = cas_match.group(1)

    trade_name = product_name
    trade_match = re.search(
        r"Trade\s+name/designation\s*:\s*(.+?)(?:\n|Product\s+No)",
        text,
        re.I | re.S,
    )
    if trade_match:
        trade_name = trade_match.group(1).strip()

    product_no = ""
    pn_match = re.search(r"Product\s+No\.?\s*:\s*(\S+)", text, re.I)
    if pn_match:
        product_no = pn_match.group(1)

    manufacturer = ""
    mfr_match = re.search(
        r"Supplier\s*\n([^\n]+)\s*\nStreet\s+([^\n]+)\s*\nPostal",
        text,
        re.I,
    )
    if mfr_match:
        manufacturer = f"{mfr_match.group(1).strip()}, {mfr_match.group(1).strip()}"

    addr_match = re.search(
        r"Supplier\s*\n([^\n]+)\s*\nStreet\s+([^\n]+)\s*\nPostal code/City\s+([^\n]+)",
        text,
        re.I,
    )
    if addr_match:
        manufacturer = (
            f"{addr_match.group(1).strip()}, {addr_match.group(2).strip()}, "
            f"{addr_match.group(3).strip()}"
        )

    recommended_use = "Laboratory Investigations"
    use_match = re.search(
        r"Relevant identified uses:\s*(.+?)(?:\n|Uses advised)",
        text,
        re.I | re.S,
    )
    if use_match:
        recommended_use = use_match.group(1).strip().rstrip(".")

    return {
        "trade_name": trade_name,
        "product_code": product_no or "—",
        "cas": cas or "—",
        "hsno": "—",
        "un": "1230",
        "dg_class": "3",
        "packing_group": "III",
        "manufacturer": manufacturer or "See original supplier documentation",
        "recommended_use": recommended_use,
    }


def extract_epa_product_codes(epa_text: str) -> dict:
    """Pull HSNO / UN / DG from scraped EPA text when present."""
    fields = {}
    if not epa_text:
        return fields
    hsno = re.search(r"HSR\d{6}", epa_text, re.I)
    if hsno:
        fields["hsno"] = hsno.group(0).upper()
    un = re.search(r"\bUN\s*(\d{4})\b", epa_text, re.I)
    if un:
        fields["un"] = un.group(1)
    dg = re.search(r"(?:DG\s*Class|Class)\s*[:\s]*([0-9.]+)", epa_text, re.I)
    if dg:
        fields["dg_class"] = dg.group(1)
    pg = re.search(r"Packing\s*group\s*[:\s#]*([IVX]+|\d+)", epa_text, re.I)
    if pg:
        fields["packing_group"] = pg.group(1).upper()
    return fields


def render_ecp_cover_section(
    *,
    product_fields: dict,
    logo_html: str = "",
) -> str:
    issue, expiry = _issue_expiry_dates()
    logo_block = logo_html or ""
    return f"""
<section class="sds-section sds-cover ecp-cover" data-section="cover">
  <div class="ecp-cover-header">
    {logo_block}
    <h1 class="ecp-title">Safety Data Sheet</h1>
    <p class="ecp-dates">Date of Issue : {issue} &nbsp;&nbsp;&nbsp; Date of Expiry: {expiry}</p>
  </div>
  <h2 class="sds-section-heading">1: IDENTIFICATION OF THE MATERIAL AND SUPPLIER</h2>
  <table class="ecp-info-table">
    <tr><th>Distributor Name</th><td>{_e(ECP_DISTRIBUTOR['name'])}</td></tr>
    <tr><th>Address</th><td>{_e(ECP_DISTRIBUTOR['address'])}</td></tr>
    <tr><th>Telephone</th><td>{_e(ECP_DISTRIBUTOR['telephone'])}</td></tr>
    <tr><th>Facsimile</th><td>{_e(ECP_DISTRIBUTOR['facsimile'])}</td></tr>
    <tr><th>Emergency phone number</th><td>{_e(ECP_DISTRIBUTOR['emergency'])}</td></tr>
  </table>
  <table class="ecp-info-table">
    <tr><th>Manufacturer Name</th><td>{_e(product_fields.get('manufacturer', ''))}</td></tr>
  </table>
  <table class="ecp-product-table">
    <thead>
      <tr>
        <th>Product</th><th>Code</th><th>CAS#</th><th>HSNO#</th><th>UN #</th>
        <th>DG Class/es</th><th>Packing group #</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>{_e(product_fields.get('trade_name', ''))}</td>
        <td>{_e(product_fields.get('product_code', ''))}</td>
        <td>{_e(product_fields.get('cas', ''))}</td>
        <td>{_e(product_fields.get('hsno', ''))}</td>
        <td>{_e(product_fields.get('un', ''))}</td>
        <td>{_e(product_fields.get('dg_class', ''))}</td>
        <td>{_e(product_fields.get('packing_group', ''))}</td>
      </tr>
    </tbody>
  </table>
  <p><strong>Recommended use</strong> : {_e(product_fields.get('recommended_use', ''))}</p>
</section>
"""


def render_section_15_block(
    *,
    product_fields: dict,
    acute_toxic_1_or_2: bool,
) -> str:
    handler = (
        SECTION_15_ACUTE_TOXIC_HANDLER if acute_toxic_1_or_2 else SECTION_15_DEFAULT_HANDLER
    )
    hsno = product_fields.get("hsno") or "—"
    extra = ""
    if acute_toxic_1_or_2:
        extra = (
            "<p class='revised'><strong>Certified handler required. Tracked substance.</strong></p>"
        )

    return f"""
<section class="sds-section ecp-section-15" data-section="15">
  <h2 class="sds-section-heading">15: Regulatory information</h2>
  <h3>15.1 Safety, health and environmental regulations/legislation specific for the substance or mixture</h3>
  <h4>National regulatory information</h4>
  <p>HSNO Approval Code: {_e(hsno)}</p>
  <p>HSNO Group Standard Approval: HSR002596 - Laboratory Chemicals and Reagent Kits Group Standard 2006</p>
  <p>Tracking Required: {handler['tracking_required']}</p>
  <p>Approved Handler Cert.: {handler['approved_handler_cert']}</p>
  {extra}
  <h4>Notification status</h4>
  <p>NZIoC : On the inventory, or in compliance with the inventory</p>
</section>
"""


def render_section_16_disclaimer() -> str:
    return f"""
<section class="sds-section ecp-disclaimer-section" data-section="16">
  <h2 class="sds-section-heading">16: Disclaimer</h2>
  <p class="ecp-disclaimer">{_e(ECP_DISCLAIMER)}</p>
  <p class="ecp-disclaimer-end">{_e(ECP_DISCLAIMER_END_MARKER)}</p>
</section>
"""


def normalize_section_headings(body_html: str) -> str:
    """Convert SECTION N: style to ECP N: style."""
    def replacer(match: re.Match) -> str:
        num = match.group(1)
        title = match.group(2).strip()
        return f'<h2 class="sds-section-heading">{num}: {title}</h2>'

    body_html = re.sub(
        r'<h2[^>]*>\s*SECTION\s+(\d+)\s*:\s*([^<]+)</h2>',
        replacer,
        body_html,
        flags=re.IGNORECASE,
    )
    return body_html


def _strip_cover_and_tail_sections(body_html: str) -> str:
    body_html = re.sub(
        r'<section[^>]*data-section="cover"[^>]*>.*?</section>',
        "",
        body_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body_html = re.sub(
        r'<section[^>]*data-section="15"[^>]*>.*?</section>',
        "",
        body_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body_html = re.sub(
        r'<section[^>]*data-section="16"[^>]*>.*?</section>',
        "",
        body_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body_html = re.sub(
        r'<section class="preserved-original-images">.*?</section>',
        "",
        body_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return body_html.strip()


def _clean_section2_hazard_images(body_html: str) -> str:
    """Remove duplicate pictogram markup from Section 2 before deterministic inject."""
    section = re.search(
        r'(<section[^>]*data-section="2"[^>]*>)(.*?)(</section>)',
        body_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not section:
        return body_html

    open_tag, inner, close_tag = section.groups()
    inner = re.sub(
        r'<div class="sds-image-block hazard-pictograms">.*?</div>',
        "",
        inner,
        flags=re.IGNORECASE | re.DOTALL,
    )
    inner = re.sub(r"<!-- PRESERVE_IMAGE:img-\d+ -->", "", inner)
    inner = re.sub(r"<img\b[^>]*>", "", inner, flags=re.IGNORECASE)
    inner = re.sub(
        r"<h[34][^>]*>\s*Hazard\s+Pictograms?\s*</h[34]>",
        "",
        inner,
        flags=re.IGNORECASE,
    )
    cleaned = open_tag + inner + close_tag
    return body_html[: section.start()] + cleaned + body_html[section.end() :]


def inject_images_by_role(body_html: str, images: list[dict]) -> str:
    from app.services.document_image_service import DocumentImageService

    hazard_imgs = DocumentImageService.hazard_pictogram_images(images)
    if not hazard_imgs:
        return body_html

    body_html = _clean_section2_hazard_images(body_html)

    tags = "".join(
        f'<img class="preserved-original-image hazard-pictogram" '
        f'data-image-id="{_e(img["id"])}" src="{img["data_url"]}" alt="GHS hazard pictogram" />'
        for img in hazard_imgs
    )
    block = (
        '<div class="sds-image-block hazard-pictograms">'
        "<h3>Hazard Pictogram</h3>"
        f"{tags}</div>"
    )

    patterns = [
        r'(data-section="2"[^>]*>.*?Hazard\s+Pictogram[^<]*</[^>]+>)',
        r'(<section[^>]*data-section="2"[^>]*>.*?<h2[^>]*>.*?</h2>)',
        r'(<h2[^>]*>\s*2\s*:\s*[^<]*HAZARD[^<]*</h2>)',
    ]
    for pattern in patterns:
        match = re.search(pattern, body_html, re.IGNORECASE | re.DOTALL)
        if match:
            pos = match.end()
            return body_html[:pos] + block + body_html[pos:]

    section2 = re.search(
        r'(<section[^>]*data-section="2"[^>]*>)',
        body_html,
        re.IGNORECASE,
    )
    if section2:
        pos = section2.end()
        return body_html[:pos] + block + body_html[pos:]

    return block + body_html


def apply_ecp_sds_layout(
    body_html: str,
    *,
    product_fields: dict,
    images: list[dict],
    epa_hazard_text: str = "",
    comparison_result: dict | None = None,
    logo_html: str = "",
) -> str:
    """Wrap AI body with ECP cover, NZ section 15 rules, disclaimer, and image placement."""
    acute = detect_acute_toxicity_category_1_or_2(
        epa_hazard_text=epa_hazard_text,
        body_html=body_html,
        comparison_result=comparison_result,
    )

    core = _strip_cover_and_tail_sections(body_html)
    core = normalize_section_headings(core)
    core = inject_images_by_role(core, images)

    cover = render_ecp_cover_section(product_fields=product_fields, logo_html=logo_html)
    section_15 = render_section_15_block(
        product_fields=product_fields,
        acute_toxic_1_or_2=acute,
    )
    disclaimer = render_section_16_disclaimer()

    return cover + core + section_15 + disclaimer
