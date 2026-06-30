from app.services.epa_nz_extractor import extract_hazard_classifications


def collect_epa_document_context(gov_sources: list[dict]) -> dict:
    """Build EPA hazard classification context for fixed-document generation."""
    hazard_classifications: dict | None = None
    hazard_source_url: str | None = None

    for source in gov_sources:
        article_metadata = source.get("metadata") or {}
        hazard = article_metadata.get("hazard_classifications")
        if not hazard:
            hazard = extract_hazard_classifications(source.get("text") or "")

        if hazard and not hazard_classifications:
            hazard_classifications = hazard
            hazard_source_url = source.get("url")

    return {
        "hazard_classifications": hazard_classifications,
        "hazard_source_url": hazard_source_url,
        "has_epa_hazard_data": hazard_classifications is not None,
    }


def collect_gov_sources_from_workflow(workflow: dict, scraper) -> list[dict]:
    sources: list[dict] = []
    for article_id in workflow.get("gov_article_ids", []):
        article = scraper.get_article(article_id)
        if not article:
            continue
        text = (
            article.get("admin_edited_text")
            or article.get("cleaned_text")
            or article.get("extracted_text")
            or ""
        ).strip()
        if not text:
            continue
        sources.append({
            "article_id": article_id,
            "url": article["url"],
            "title": article.get("extracted_title"),
            "text": text,
            "metadata": article.get("metadata") or {},
        })
    return sources
