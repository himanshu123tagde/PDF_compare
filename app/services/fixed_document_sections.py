import html
import re


def _e(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def render_hazard_classifications_section(hazard_data: dict, *, inline: bool = False) -> str:
    """Render EPA hazard classifications verbatim as an HTML table."""
    rows = hazard_data.get("rows") or []
    heading = hazard_data.get("heading", "Hazard Classifications")
    heading_tag = "h3" if inline else "h2"
    wrapper_open = (
        '<div class="epa-hazard-classifications revised">'
        if inline
        else '<section class="epa-hazard-classifications">'
    )
    wrapper_close = "</div>" if inline else "</section>"

    if not rows:
        raw_text = (hazard_data.get("raw_text") or "").strip()
        if not raw_text:
            return ""
        return (
            f"{wrapper_open}"
            f"<{heading_tag}>{_e(heading)}</{heading_tag}>"
            f"<p>{_e(raw_text)}</p>"
            f"{wrapper_close}"
        )

    header_cells = rows[0]
    body_rows = rows[1:] if len(rows) > 1 else rows

    if len(header_cells) >= 2 and not any(
        keyword in header_cells[0].lower()
        for keyword in ("hazard", "classification", "statement", "category")
    ):
        header_html = (
            "<thead><tr>"
            f"<th>{_e(header_cells[0])}</th>"
            f"<th>{_e(header_cells[1])}</th>"
            "</tr></thead>"
        )
        body_rows = rows[1:] if len(rows) > 1 else rows
    else:
        header_html = (
            "<thead><tr>"
            "<th>Hazard</th><th>Classification</th>"
            "</tr></thead>"
        )
        body_rows = rows

    table_body = "<tbody>"
    for row in body_rows:
        cells = row + [""] * max(0, 2 - len(row))
        table_body += (
            "<tr>"
            f"<td>{_e(cells[0])}</td>"
            f"<td>{_e(cells[1])}</td>"
            "</tr>"
        )
    table_body += "</tbody>"

    return (
        f"{wrapper_open}"
        f"<{heading_tag}>{_e(heading)}</{heading_tag}>"
        f"<table>{header_html}{table_body}</table>"
        '<p class="epa-source-note"><em>Source: EPA New Zealand — official hazard classification data.</em></p>'
        f"{wrapper_close}"
    )


def _strip_section(body_html: str, keywords: tuple[str, ...]) -> str:
    pattern = re.compile(
        r"(<section[^>]*>.*?<h2[^>]*>.*?(?:"
        + "|".join(re.escape(k) for k in keywords)
        + r").*?</h2>.*?</section>)",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub("", body_html, count=1)


def _inject_into_sds_section(body_html: str, section_num: str, content_html: str) -> str:
    if not content_html:
        return body_html
    pattern = re.compile(
        rf'(<section[^>]*\bdata-section="{re.escape(section_num)}"[^>]*>.*?<h2[^>]*>.*?</h2>)',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(body_html)
    if match:
        insert_pos = match.end()
        return body_html[:insert_pos] + content_html + body_html[insert_pos:]
    return body_html + content_html


def inject_mandatory_sections(
    body_html: str,
    *,
    hazard_section_html: str = "",
    sds_profile: dict | None = None,
) -> str:
    """Ensure EPA hazard data appears in the document (Section 2 for SDS)."""
    is_sds = bool(sds_profile and sds_profile.get("is_sds"))

    if is_sds:
        result = body_html.strip()
        if hazard_section_html:
            result = _strip_section(result, ("hazard classification", "hazard classifications"))
            result = _inject_into_sds_section(result, "2", hazard_section_html)
        return result

    result = body_html.strip()
    if hazard_section_html:
        result = _strip_section(result, ("hazard classification", "hazard classifications"))
        result = hazard_section_html + result
    return result


def render_preserved_image_tag(image: dict) -> str:
    """Render an original document image unchanged as an HTML img tag."""
    return (
        f'<img class="preserved-original-image" '
        f'data-image-id="{_e(image["id"])}" '
        f'src="{image["data_url"]}" '
        f'alt="Original document image {_e(image["id"])}" />'
    )


def _replace_image_src(body_html: str, image_id: str, data_url: str) -> str:
    pattern = re.compile(
        rf'(<img\b[^>]*\bdata-image-id="{re.escape(image_id)}"[^>]*\bsrc=")([^"]*)(")',
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: f"{m.group(1)}{data_url}{m.group(3)}", body_html)


def _remove_ai_generated_images(body_html: str, preserved_ids: set[str]) -> str:
    """Remove img tags the AI invented that are not from the original document."""
    def replacer(match: re.Match) -> str:
        tag = match.group(0)
        for image_id in preserved_ids:
            if f'data-image-id="{image_id}"' in tag:
                return tag
        return ""

    return re.sub(r"<img\b[^>]*>", replacer, body_html, flags=re.IGNORECASE)


def inject_preserved_images(
    body_html: str,
    images: list[dict],
    *,
    append_missing: bool = True,
    exclude_roles: frozenset[str] | None = None,
) -> str:
    """
    Ensure every original document image appears unchanged in the generated HTML.
    Replaces placeholders and restores correct src if the AI modified them.
    """
    if not images:
        return body_html

    if exclude_roles:
        images = [img for img in images if img.get("role") not in exclude_roles]
        if not images:
            return body_html

    preserved_ids = {image["id"] for image in images}
    result = _remove_ai_generated_images(body_html, preserved_ids)
    missing_tags: list[str] = []

    for image in images:
        image_id = image["id"]
        tag = render_preserved_image_tag(image)
        placeholder = f"<!-- PRESERVE_IMAGE:{image_id} -->"

        if placeholder in result:
            result = result.replace(placeholder, tag)
            continue

        if f'data-image-id="{image_id}"' in result:
            result = _replace_image_src(result, image_id, image["data_url"])
            continue

        missing_tags.append(tag)

    if missing_tags and append_missing:
        figures = "".join(
            f'<figure class="preserved-figure">{tag}</figure>' for tag in missing_tags
        )
        result += (
            '<section class="preserved-original-images">'
            "<h2>Original Document Images</h2>"
            f"{figures}"
            "</section>"
        )

    return result
