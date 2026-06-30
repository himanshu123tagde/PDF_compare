import json

from pathlib import Path

from app.services.sds_structure_extractor import build_sds_structure_prompt_block
_FIXED_DOC_PROMPT_PATH = Path(__file__).parent / "fixed_document_system_prompt.txt"

FIXED_DOCUMENT_OUTPUT_SCHEMA = {
    "document_title": "SDS title matching the uploaded document (e.g. Safety Data Sheet — Product Name)",
    "body_html": (
        "Semantic HTML fragment for the full SDS body. "
        "For SDS documents: use <section class='sds-section' data-section='N'> per section "
        "and <h2 class='sds-section-heading'> for headings matching the uploaded style. "
        "Mark new or revised blocks with class='revised'."
    ),
}


def load_fixed_document_system_prompt() -> str:
    return _FIXED_DOC_PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_fixed_document_prompt(
    *,
    product_name: str,
    description: str | None,
    company_filename: str,
    company_text: str,
    comparison_result: dict,
    epa_context: dict | None = None,
    preserved_images: list[dict] | None = None,
    sds_profile: dict | None = None,
) -> str:
    context = description.strip() if description else "Not provided."

    epa_blocks: list[str] = []
    if epa_context:
        hazard = epa_context.get("hazard_classifications")
        if hazard:
            epa_blocks.append(
                "=== EPA HAZARD CLASSIFICATIONS (MUST USE VERBATIM) ===\n"
                f"Source URL: {epa_context.get('hazard_source_url') or 'EPA AHSC record'}\n"
                f"Data:\n{hazard.get('raw_text') or json.dumps(hazard.get('rows'), indent=2)}\n"
                "Instruction: Include this hazard classification data exactly as provided. "
                "Do not paraphrase, omit rows, or invent classifications."
            )

    epa_section = ""
    if epa_blocks:
        epa_section = "\n\n".join(epa_blocks) + "\n\n"

    image_section = ""
    if preserved_images:
        hazard_count = sum(
            1 for image in preserved_images if image.get("role") == "hazard_pictograms"
        )
        image_lines = [
            "=== ORIGINAL DOCUMENT IMAGES ===",
            f"The uploaded SDS contains {hazard_count} hazard pictogram(s) on page 2.",
            "Rules:",
            "- Do NOT recreate, redraw, replace, or describe pictograms as text.",
            "- Do NOT generate <img> tags or <!-- PRESERVE_IMAGE --> placeholders.",
            "- The system injects the ECP logo on the cover and hazard pictograms in Section 2.",
            "- In Section 2 you may include a 'Hazard Pictogram' subheading with no images under it.",
        ]
        image_section = "\n".join(image_lines) + "\n\n"

    sds_section = ""
    if sds_profile and sds_profile.get("is_sds"):
        sds_section = build_sds_structure_prompt_block(sds_profile) + "\n\n"

    return (
        f"PRODUCT: {product_name}\n"
        f"CONTEXT: {context}\n\n"
        f"{sds_section}"
        f"{epa_section}"
        f"{image_section}"
        f"=== ORIGINAL COMPANY SDS / DOCUMENT ===\n"
        f"Filename: {company_filename}\n"
        f"Text:\n{company_text}\n\n"
        f"=== COMPLIANCE COMPARISON RESULT (JSON) ===\n"
        f"{json.dumps(comparison_result, indent=2)}\n\n"
        f"=== OUTPUT INSTRUCTIONS ===\n"
        f"Produce a complete Safety Data Sheet (SDS) that fixes missing coverage and "
        f"resolves conflicts identified in the comparison, using the same style and "
        f"section structure as the uploaded document.\n"
        f"Return a single JSON object matching this schema exactly:\n"
        f"{json.dumps(FIXED_DOCUMENT_OUTPUT_SCHEMA, indent=2)}\n\n"
        "Priority rules:\n"
        "1. HAZARD CLASSIFICATIONS: If EPA hazard data is provided above, that section must "
        "use the exact EPA values — same hazards, categories, and H-statements.\n"
        "2. Do not invent hazard classes not present in the EPA data.\n"
        "3. IMAGES: Never add <img> tags or image placeholders — the system injects the ECP logo and Section 2 pictograms.\n"
        "4. SDS STYLE (ECP NZ): Use ECP Limited NZ SDS format:\n"
        "   - Do NOT generate Section 1 cover or Section 16 disclaimer — the system adds these.\n"
        "   - Generate sections 2–14 only, each as "
        "<section class='sds-section' data-section='N'> with "
        "<h2 class='sds-section-heading'>N: TITLE</h2> (ECP numbering, not 'SECTION N').\n"
        "   - Section 2 must include a 'Hazard Pictogram' subheading; leave "
        "<!-- PRESERVE_IMAGE:img-NNN --> placeholders for pictograms.\n"
        "   - Section 13: NZ disposal considerations per EPA / NZ regulations.\n"
        "   - Do NOT generate Section 15 — the system adds NZ regulatory handler/tracking info.\n"
        "- body_html must be a self-contained document body suitable for PDF rendering.\n"
        "- Do not include <html>, <head>, or <body> tags — only the inner content.\n"
        "- Return JSON only, with no markdown fences or extra commentary."
    )

