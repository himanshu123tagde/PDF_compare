import re

# GHS / HSNO standard 16-section SDS titles (used when sections are not fully detected).
STANDARD_SDS_SECTIONS: list[tuple[int, str]] = [
    (1, "Identification"),
    (2, "Hazards identification"),
    (3, "Composition/information on ingredients"),
    (4, "First aid measures"),
    (5, "Fire-fighting measures"),
    (6, "Accidental release measures"),
    (7, "Handling and storage"),
    (8, "Exposure controls/personal protection"),
    (9, "Physical and chemical properties"),
    (10, "Stability and reactivity"),
    (11, "Toxicological information"),
    (12, "Ecological information"),
    (13, "Disposal considerations"),
    (14, "Transport information"),
    (15, "Regulatory information"),
    (16, "Other information"),
]

_SDS_KEYWORDS = re.compile(
    r"\b(?:safety\s+data\s+sheet|material\s+safety\s+data\s+sheet|\bsds\b|\bmsds\b)\b",
    re.IGNORECASE,
)

_SECTION_LINE_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"^(?:SECTION\s+)?(\d{1,2})\s*[\.:\-–]\s*(.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Section\s+(\d{1,2})\s*[-–:]\s*(.+?)\s*$",
        re.IGNORECASE,
    ),
]

_HEADING_STYLE_SECTION_UPPER = "section_n_colon_upper"
_HEADING_STYLE_SECTION_TITLE = "section_n_colon_title"
_HEADING_STYLE_NUMBER_DOT = "number_dot_title"


def _normalize_section_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    cleaned = re.sub(r"\.+$", "", cleaned)
    return cleaned


def _infer_heading_style(raw_heading: str, number: int, title: str) -> str:
    if re.match(rf"^SECTION\s+{number}\s*:", raw_heading, re.IGNORECASE):
        if raw_heading.isupper() or title.isupper():
            return _HEADING_STYLE_SECTION_UPPER
        return _HEADING_STYLE_SECTION_TITLE
    if re.match(rf"^Section\s+{number}\s*:", raw_heading, re.IGNORECASE):
        return _HEADING_STYLE_SECTION_TITLE
    return _HEADING_STYLE_NUMBER_DOT


def _format_section_heading(number: int, title: str, style: str) -> str:
    if style == _HEADING_STYLE_SECTION_UPPER:
        return f"SECTION {number}: {title.upper()}"
    if style == _HEADING_STYLE_SECTION_TITLE:
        return f"Section {number}: {title}"
    return f"{number}. {title}"


def _detect_document_title(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:12]:
        if _SDS_KEYWORDS.search(line):
            return line
        if re.search(r"safety\s+data\s+sheet", line, re.IGNORECASE):
            return line
    return None


def _extract_sections_from_text(text: str) -> list[dict]:
    sections: list[dict] = []
    seen_numbers: set[int] = set()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            continue
        for pattern in _SECTION_LINE_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            number = int(match.group(1))
            if number < 1 or number > 16 or number in seen_numbers:
                continue
            title = _normalize_section_title(match.group(2))
            if not title or len(title) < 3:
                continue
            seen_numbers.add(number)
            sections.append({
                "number": number,
                "title": title,
                "heading_text": stripped,
                "heading_style": _infer_heading_style(stripped, number, title),
            })
            break

    sections.sort(key=lambda item: item["number"])
    return sections


def is_likely_sds(text: str, filename: str = "") -> bool:
    sample = (text or "")[:4000]
    if _SDS_KEYWORDS.search(sample):
        return True
    if re.search(r"safety\s+data\s+sheet", sample, re.IGNORECASE):
        return True
    if re.search(r"\bsds\b", filename, re.IGNORECASE):
        return True
    sections = _extract_sections_from_text(sample)
    return len(sections) >= 3


def extract_sds_profile(text: str, filename: str = "") -> dict:
    """Extract SDS structure and heading style from uploaded document text."""
    is_sds = is_likely_sds(text, filename)
    sections = _extract_sections_from_text(text)

    if is_sds and len(sections) < 8:
        existing = {section["number"] for section in sections}
        for number, title in STANDARD_SDS_SECTIONS:
            if number in existing:
                continue
            style = (
                sections[0]["heading_style"]
                if sections
                else _HEADING_STYLE_SECTION_UPPER
            )
            sections.append({
                "number": number,
                "title": title,
                "heading_text": _format_section_heading(number, title, style),
                "heading_style": style,
                "inferred": True,
            })
        sections.sort(key=lambda item: item["number"])

    heading_style = sections[0]["heading_style"] if sections else _HEADING_STYLE_SECTION_UPPER
    document_title = _detect_document_title(text) or "Safety Data Sheet"

    return {
        "is_sds": is_sds,
        "document_title": document_title,
        "heading_style": heading_style,
        "sections": sections,
        "section_count": len(sections),
    }


def ensure_sds_profile(text: str, filename: str = "") -> dict:
    """
    Return an SDS profile for generation. Company uploads are always treated as SDS;
    section headings and style are taken from the uploaded document when detectable.
    """
    profile = extract_sds_profile(text, filename)
    if profile.get("is_sds") and profile.get("sections"):
        return profile

    style = profile.get("heading_style") or _HEADING_STYLE_SECTION_UPPER
    sections = profile.get("sections") or []
    existing = {section["number"] for section in sections}

    for number, title in STANDARD_SDS_SECTIONS:
        if number in existing:
            continue
        sections.append({
            "number": number,
            "title": title,
            "heading_text": _format_section_heading(number, title, style),
            "heading_style": style,
            "inferred": True,
        })

    sections.sort(key=lambda item: item["number"])
    return {
        "is_sds": True,
        "document_title": profile.get("document_title") or "Safety Data Sheet",
        "heading_style": style,
        "sections": sections,
        "section_count": len(sections),
    }


def build_sds_structure_prompt_block(profile: dict) -> str:
    if not profile.get("is_sds"):
        return ""

    lines = [
        "=== SDS FORMAT (MATCH UPLOADED DOCUMENT STYLE) ===",
        "Document type: Safety Data Sheet (SDS).",
        f"Original document title style: {profile.get('document_title', 'Safety Data Sheet')}",
        f"Section heading style: {profile.get('heading_style', _HEADING_STYLE_SECTION_UPPER)}",
        "",
        "Use the same section order, numbering, and heading format as the uploaded SDS.",
        "Wrap each section in: <section class=\"sds-section\" data-section=\"N\">",
        "Use <h2 class=\"sds-section-heading\"> for section headings exactly as listed below.",
        "",
        "Sections (preserve order and heading text):",
    ]

    for section in profile.get("sections") or []:
        inferred = " (standard section — add if missing)" if section.get("inferred") else ""
        lines.append(
            f"  {section['number']}. {section['heading_text']}{inferred}"
        )

    lines.extend([
        "",
        "SDS layout rules:",
        "- Keep the overall SDS layout like the uploaded PDF: numbered sections, tables for "
        "properties/hazards, label-style blocks where the original used them.",
        "- Do not convert the SDS into a narrative report or letter format.",
        "- Preserve unchanged sections verbatim; only revise sections with compliance gaps.",
        "- Section 2 (Hazards): use EPA hazard classification data when provided.",
        "- Section 13 (Disposal): use knowledge-base disposal requirements when matched.",
        "- Use tables (<table>) where the original SDS used tabular data.",
    ])
    return "\n".join(lines)
