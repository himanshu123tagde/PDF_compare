import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

EPA_AHSC_VIEW_PATH = "/database-search/approved-hazardous-substances-with-controls/view/"


def is_epa_ahsc_view_page(url: str) -> bool:
    parsed = urlparse(url)
    if "epa.govt.nz" not in parsed.netloc.lower():
        return False
    return EPA_AHSC_VIEW_PATH.lower() in parsed.path.lower()


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if cleaned in ("", "\xa0", "&nbsp;"):
        return ""
    return cleaned


def _accordion_heading(row) -> str:
    title_el = row.select_one(".accordion__title")
    if not title_el:
        return ""

    for tag in title_el.select("i, svg"):
        tag.decompose()

    return _clean_text(title_el.get_text())


def _format_description_list(dl) -> list[str]:
    lines: list[str] = []
    for dt in dl.select("dt.description-list__term"):
        term = _clean_text(dt.get_text()).rstrip(":")
        dd = dt.find_next_sibling("dd")
        value = _clean_text(dd.get_text()) if dd else ""
        if term:
            lines.append(f"{term}: {value}" if value else f"{term}:")
    return lines


def _format_hazard_table(table) -> list[str]:
    lines: list[str] = []
    for row in table.select("tr"):
        cells = [_clean_text(cell.get_text()) for cell in row.select("td")]
        cells = [cell for cell in cells if cell]
        if cells:
            lines.append(" | ".join(cells))
    return lines


def extract_epa_ahsc_record(html: str) -> tuple[str | None, str | None]:
    """
    Extract a structured hazardous-substance record from EPA NZ AHSC view pages.
    Targets only main content accordions and preserves section headings.
    """
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("main#main .block--content") or soup.select_one("main#main")
    if not content:
        return None, None

    substance_name = None
    h1 = content.find("h1")
    if h1:
        substance_name = _clean_text(h1.get_text())

    sections: list[str] = []
    if substance_name:
        sections.append(f"# {substance_name}")

    rows = content.select(".accordion__row")
    for row in rows:
        heading = _accordion_heading(row)
        if not heading:
            continue

        section_lines = [f"## {heading}"]
        content_div = row.select_one(".accordion__content")
        if content_div:
            for dl in content_div.select("dl.description-list"):
                section_lines.extend(_format_description_list(dl))
            for table in content_div.select("table.accordion__table"):
                section_lines.extend(_format_hazard_table(table))

        sections.append("\n".join(section_lines))

    text = "\n\n".join(sections).strip()
    if not text:
        return substance_name, None

    return substance_name, text


_REGULATION_LINE_RE = re.compile(
    r"^(?:Regulation|Variation|Notice)\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def normalize_regulation_name(name: str) -> str:
    """Normalize an EPA regulation/notice name for deduplication."""
    cleaned = re.sub(r"\s+", " ", name).strip().lower()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return cleaned


_HAZARD_SECTION_RE = re.compile(
    r"^##\s+Hazard\s+Classifications\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def extract_hazard_classifications(text: str) -> dict | None:
    """Extract the Hazard Classifications accordion section from EPA AHSC text."""
    match = _HAZARD_SECTION_RE.search(text)
    if not match:
        return None

    start = match.end()
    next_section = re.search(r"^##\s+", text[start:], re.MULTILINE)
    section_text = text[start: start + next_section.start()] if next_section else text[start:]
    section_text = section_text.strip()
    if not section_text:
        return None

    rows: list[list[str]] = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if cells:
            rows.append(cells)

    return {
        "heading": "Hazard Classifications",
        "rows": rows,
        "raw_text": section_text,
        "source": "epa_ahsc",
    }


def extract_epa_structured_metadata(html: str, text: str | None = None) -> dict:
    """Build structured EPA fields stored on scraped articles."""
    metadata: dict = {
        "regulation_references": extract_regulation_references(text or ""),
    }

    hazard = extract_hazard_classifications(text or "")
    if hazard:
        metadata["hazard_classifications"] = hazard

    if html and not hazard:
        soup = BeautifulSoup(html, "lxml")
        for row in soup.select(".accordion__row"):
            heading = _accordion_heading(row)
            if not heading or "hazard classification" not in heading.lower():
                continue
            table_rows: list[list[str]] = []
            content_div = row.select_one(".accordion__content")
            if content_div:
                for table in content_div.select("table.accordion__table"):
                    for tr in table.select("tr"):
                        cells = [_clean_text(cell.get_text()) for cell in tr.select("td")]
                        cells = [cell for cell in cells if cell]
                        if cells:
                            table_rows.append(cells)
            if table_rows:
                metadata["hazard_classifications"] = {
                    "heading": heading,
                    "rows": table_rows,
                    "raw_text": "\n".join(" | ".join(r) for r in table_rows),
                    "source": "epa_ahsc",
                }
            break

    return metadata


def extract_regulation_references(text: str) -> list[str]:
    """
    Extract regulation/notice names from EPA AHSC accordion text.
    Matches lines like 'Regulation: Part 10' or 'Variation: Labelling Notice 2017'.
    """
    seen: set[str] = set()
    refs: list[str] = []
    for match in _REGULATION_LINE_RE.finditer(text):
        name = _clean_text(match.group(1))
        if not name:
            continue
        key = normalize_regulation_name(name)
        if key not in seen:
            seen.add(key)
            refs.append(name)
    return refs
