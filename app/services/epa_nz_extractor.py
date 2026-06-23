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
