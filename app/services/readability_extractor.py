import logging

logger = logging.getLogger(__name__)


def extract_with_readability(html: str) -> tuple[str | None, str | None]:
    try:
        from readability import Document
        from bs4 import BeautifulSoup

        doc = Document(html)
        title = doc.title()

        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        return title, text

    except Exception as e:
        logger.error("Readability extraction failed: %s", e)
        return None, None