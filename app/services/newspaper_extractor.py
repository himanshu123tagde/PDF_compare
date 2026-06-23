import logging

logger = logging.getLogger(__name__)


def extract_with_newspaper(url: str, html: str) -> tuple[str | None, str | None, dict]:
    """
    Extract article using newspaper4k.
    Returns (title, text, metadata_dict).
    """
    try:
        from newspaper import Article

        article = Article(url)
        article.download(input_html=html)
        article.parse()

        title = article.title if article.title else None
        text = article.text if article.text else None

        metadata = {
            "authors": article.authors or [],
            "publish_date": str(article.publish_date) if article.publish_date else None,
            "top_image": article.top_image or None,
            "summary": None,
        }

        # Try NLP for summary
        try:
            article.nlp()
            metadata["summary"] = article.summary if article.summary else None
            metadata["keywords"] = article.keywords if article.keywords else []
        except Exception:
            metadata["keywords"] = []

        return title, text, metadata

    except Exception as e:
        logger.error("newspaper4k extraction failed: %s", e)
        return None, None, {}