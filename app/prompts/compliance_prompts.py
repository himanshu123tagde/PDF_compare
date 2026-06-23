import json
from pathlib import Path

from app.prompts.compliance_output_schema import COMPARISON_OUTPUT_SCHEMA

_PROMPT_PATH = Path(__file__).parent / "compliance_system_prompt.txt"


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_user_prompt(
    *,
    product_name: str,
    description: str | None,
    gov_sources: list[dict],
    company_filename: str,
    company_text: str,
) -> str:
    gov_blocks: list[str] = []
    for index, source in enumerate(gov_sources, start=1):
        gov_blocks.append(
            f"--- Source {index} ---\n"
            f"URL: {source['url']}\n"
            f"Title: {source.get('title') or 'N/A'}\n"
            f"Text:\n{source['text']}"
        )

    context = description.strip() if description else "Not provided."

    return (
        f"PRODUCT: {product_name}\n"
        f"CONTEXT: {context}\n\n"
        f"=== GOVERNMENT SOURCES ===\n"
        f"{chr(10).join(gov_blocks)}\n\n"
        f"=== COMPANY DOCUMENT ===\n"
        f"Filename: {company_filename}\n"
        f"Text:\n{company_text}\n\n"
        f"=== OUTPUT INSTRUCTIONS ===\n"
        f"Return a single JSON object matching this schema exactly:\n"
        f"{json.dumps(COMPARISON_OUTPUT_SCHEMA, indent=2)}\n\n"
        "Mandatory analysis rules:\n"
        "- Classify each gov_requirement by evidence_depth before aligning.\n"
        "- Notice titles and Description fields like 'Requirements for labelling of "
        "hazardous substances' are regulatory_reference — NOT detailed_obligation.\n"
        "- Use cannot_verify when government evidence is shallow and company is silent.\n"
        "- Use missing only when a detailed_obligation exists and company lacks coverage.\n"
        "- conflicts[] must include government_excerpt AND company_excerpt — empty if none.\n"
        "- Set compliance_level to undetermined when most items are regulatory_reference "
        "or assessment_confidence is low.\n"
        "- Set overall_compliance_score to null unless confidence is high and >=3 "
        "detailed_obligation items exist.\n"
        "- Populate missing_evidence with topics lacking detailed government rule text.\n"
        "- Do not claim non_compliant based on company silence alone.\n"
        "- Return JSON only, with no markdown fences or extra commentary."
    )
