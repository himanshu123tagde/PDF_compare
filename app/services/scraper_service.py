import uuid
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.config import settings
from app.services.content_cleaner import clean_text
from app.services.storage_service import StorageService
from app.services.url_validator import validate_public_url
from app.services.readability_extractor import extract_with_readability
from app.services.newspaper_extractor import extract_with_newspaper
from app.services.playwright_fetcher import fetch_with_playwright
from app.services.document_extractor import is_document_url, download_and_extract_document
from app.services.scrape_limiter import scrape_semaphore
from app.services.epa_nz_extractor import is_epa_ahsc_view_page, extract_epa_ahsc_record

logger = logging.getLogger(__name__)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class ScraperService:
    def __init__(self):
        self.storage = StorageService()
        self.min_length = settings.MIN_CONTENT_LENGTH

    def _is_good_extraction(self, text: str | None) -> bool:
        if not text:
            return False
        return len(text.strip()) >= self.min_length

    async def fetch_html(self, url: str) -> str:
        """Fetch HTML with multiple header strategies."""
        headers_list = [
            {
                "User-Agent": settings.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
            },
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Safari/605.1.15"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) "
                    "Gecko/20100101 Firefox/122.0"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ]

        last_error = None

        for headers in headers_list:
            try:
                async with httpx.AsyncClient(
                    timeout=settings.REQUEST_TIMEOUT,
                    follow_redirects=True,
                    headers=headers,
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    html = response.text

                    if len(html) > 500:
                        return html

            except Exception as e:
                last_error = e
                logger.warning("Fetch attempt failed: %s", e)
                continue

        if last_error:
            raise last_error

        raise ValueError("All fetch attempts returned empty content.")

    def _content_word_count(self, text: str | None) -> int:
        if not text:
            return 0
        return len(clean_text(text).split())

    def extract_with_trafilatura(self, html: str, url: str) -> tuple[str | None, str | None]:
        metadata = trafilatura.extract_metadata(html, default_url=url)
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )
        title = metadata.title if metadata else None
        return title, text

    def extract_with_bs4(self, html: str) -> tuple[str | None, str | None]:
        soup = BeautifulSoup(html, "lxml")

        for tag in soup(["script", "style", "noscript", "header", "footer",
                         "nav", "aside", "form", "iframe", "svg", "button",
                         "input", "select", "textarea"]):
            tag.decompose()

        for tag in soup.find_all(attrs={"aria-hidden": "true"}):
            tag.decompose()
        for tag in soup.find_all(style=lambda s: s and "display:none" in s.replace(" ", "")):
            tag.decompose()
        for tag in soup.find_all(style=lambda s: s and "visibility:hidden" in s.replace(" ", "")):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else None

        if not title or len(title) < 5:
            for heading in soup.find_all(["h1", "h2"]):
                heading_text = heading.get_text(strip=True)
                if len(heading_text) > 10:
                    title = heading_text
                    break

        selectors = [
            "article", '[role="main"]', ".article-content",
            ".article-body", ".story-body", ".post-content",
            ".entry-content", ".content-body", "#article-body",
            "#story-body", "main", "#content", ".content",
        ]

        best_text = ""
        for selector in selectors:
            for element in soup.select(selector):
                text = element.get_text(separator="\n", strip=True)
                if len(text) > len(best_text):
                    best_text = text

        if self._is_good_extraction(best_text):
            return title, best_text

        paragraphs = [
            p.get_text(strip=True)
            for p in soup.find_all("p")
            if len(p.get_text(strip=True)) > 30
        ]
        if paragraphs:
            para_text = "\n\n".join(paragraphs)
            if len(para_text) > len(best_text):
                best_text = para_text

        if self._is_good_extraction(best_text):
            return title, best_text

        for div in soup.find_all(["div", "section"]):
            text = div.get_text(separator="\n", strip=True)
            if len(text) > len(best_text):
                best_text = text

        if self._is_good_extraction(best_text):
            return title, best_text

        body = soup.body
        if body:
            return title, body.get_text(separator="\n", strip=True)

        return title, None

    def _try_all_extractors(
        self, html: str, url: str
    ) -> tuple[str | None, str | None, str | None, dict]:

        metadata = {}
        candidates: list[tuple[str | None, str | None, str, dict]] = []

        if is_epa_ahsc_view_page(url):
            epa_title, epa_text = extract_epa_ahsc_record(html)
            if self._is_good_extraction(epa_text):
                return epa_title, epa_text, "epa_ahsc", metadata

        title, text = self.extract_with_trafilatura(html, url)
        if self._is_good_extraction(text):
            candidates.append((title, text, "trafilatura", metadata))

        np_title, np_text, np_metadata = extract_with_newspaper(url, html)
        if self._is_good_extraction(np_text):
            candidates.append((np_title or title, np_text, "newspaper4k", np_metadata))

        bs4_title, bs4_text = self.extract_with_bs4(html)
        if self._is_good_extraction(bs4_text):
            candidates.append((bs4_title or title, bs4_text, "beautifulsoup", metadata))

        read_title, read_text = extract_with_readability(html)
        if self._is_good_extraction(read_text):
            candidates.append((read_title or title, read_text, "readability", metadata))

        if not candidates:
            return title, text, None, metadata

        best_title, best_text, best_method, best_metadata = max(
            candidates,
            key=lambda c: self._content_word_count(c[1]),
        )
        return best_title, best_text, best_method, best_metadata

    async def _run_extraction_pipeline(self, url: str) -> dict:
        extraction_log = []
        html = None
        title = None
        text = None
        method = None
        metadata = {}

        # Fetch HTML
        logger.info("Fetching: %s", url)
        try:
            html = await self.fetch_html(url)
            extraction_log.append(f"fetch: success ({len(html)} chars)")
        except Exception as e:
            logger.warning("Fetch failed: %s", e)
            extraction_log.append(f"fetch: failed ({e})")

        # Try all extractors
        if html:
            title, text, method, metadata = self._try_all_extractors(html, url)

            if method:
                extraction_log.append(f"extraction: {method}")
                cleaned_check = clean_text(text or "")
                min_words = max(30, self.min_length // 5)
                if not cleaned_check or len(cleaned_check.split()) < min_words:
                    extraction_log.append(
                        f"quality check: {method} returned too little content "
                        f"({len(cleaned_check.split())} words after cleaning, "
                        f"need {min_words}), will try Playwright"
                    )
                    method = None
            else:
                extraction_log.append("extraction: all layers failed with basic fetch")
                
        # Fallback to Playwright if basic fetch yielded no valid extraction
        if not method:
            logger.info("Basic fetch yielded poor results, falling back to Playwright for: %s", url)
            extraction_log.append("playwright: starting fallback fetch")
            
            pw_html = await fetch_with_playwright(url)
            if pw_html:
                extraction_log.append(f"playwright: success ({len(pw_html)} chars)")
                html = pw_html
                title, text, method, metadata = self._try_all_extractors(html, url)
                
                if method:
                    extraction_log.append(f"playwright extraction: {method}")
                else:
                    extraction_log.append("playwright extraction: all layers failed")
            else:
                extraction_log.append("playwright: fetch returned empty or failed internally")

        return {
            "html": html,
            "title": title,
            "text": text,
            "method": method,
            "metadata": metadata,
            "extraction_log": extraction_log,
        }

    async def scrape_url(self, url: str) -> dict:
        async with scrape_semaphore:
            return await self._scrape_url(url)

    async def _scrape_url(self, url: str) -> dict:
        validate_public_url(url)

        article_id = str(uuid.uuid4())
        now = utcnow_iso()
        domain = urlparse(url).netloc

        article = {
            "id": article_id,
            "url": url,
            "domain": domain,
            "status": "pending",
            "extracted_title": None,
            "extracted_text": None,
            "cleaned_text": None,
            "admin_edited_text": None,
            "ai_regenerated_text": None,
            "extraction_method": None,
            "extraction_log": [],
            "metadata": {},
            "error_message": None,
            "raw_html_path": None,
            "word_count": 0,
            "created_at": now,
            "updated_at": now,
        }

        self.storage.save_article(article_id, article)

        try:
            # Check if URL points to a document (PDF, DOCX, etc.)
            if is_document_url(url):
                return await self._scrape_document(article_id, article, url)

            result = await self._run_extraction_pipeline(url)

            html = result["html"]
            title = result["title"]
            text = result["text"]
            method = result["method"]
            metadata = result["metadata"]
            extraction_log = result["extraction_log"]

            raw_html_path = None
            if html:
                raw_html_path = self.storage.save_raw_html(article_id, html)

            cleaned = clean_text(text or "")
            word_count = len(cleaned.split()) if cleaned else 0

            if method:
                status = "success"
                error_message = None
            else:
                status = "failed"
                error_message = "All extraction methods returned weak/empty content."

            article.update({
                "status": status,
                "extracted_title": title,
                "extracted_text": text,
                "cleaned_text": cleaned,
                "extraction_method": method,
                "extraction_log": extraction_log,
                "metadata": metadata,
                "raw_html_path": raw_html_path,
                "word_count": word_count,
                "error_message": error_message,
                "updated_at": utcnow_iso(),
            })

            self.storage.save_article(article_id, article)
            return article

        except Exception as e:
            logger.error("Scrape failed for %s: %s", url, e)
            article.update({
                "status": "failed",
                "error_message": str(e),
                "updated_at": utcnow_iso(),
            })
            self.storage.save_article(article_id, article)
            return article

    async def _scrape_document(self, article_id: str, article: dict, url: str) -> dict:
        """Handle document URLs (PDF, DOCX, XLSX, PPTX, etc.)."""
        extraction_log = []

        try:
            extraction_log.append("document: detected document URL")
            title, text, doc_type = await download_and_extract_document(url)

            if text and len(text.strip()) >= self.min_length:
                cleaned = clean_text(text)
                word_count = len(cleaned.split()) if cleaned else 0

                article.update({
                    "status": "success",
                    "extracted_title": title,
                    "extracted_text": text,
                    "cleaned_text": cleaned,
                    "extraction_method": f"document ({doc_type})",
                    "extraction_log": extraction_log + [
                        f"document: extracted {len(text)} chars ({doc_type})"
                    ],
                    "word_count": word_count,
                    "updated_at": utcnow_iso(),
                })
            else:
                article.update({
                    "status": "failed",
                    "extracted_title": title,
                    "extraction_method": None,
                    "extraction_log": extraction_log + [
                        f"document: extraction returned weak/empty content ({doc_type})"
                    ],
                    "error_message": "Document extraction returned weak/empty content.",
                    "updated_at": utcnow_iso(),
                })

        except Exception as e:
            logger.error("Document scrape failed for %s: %s", url, e)
            article.update({
                "status": "failed",
                "error_message": str(e),
                "extraction_log": extraction_log + [f"document: failed ({e})"],
                "updated_at": utcnow_iso(),
            })

        self.storage.save_article(article_id, article)
        return article

    def get_article(self, article_id: str) -> dict | None:
        return self.storage.load_article(article_id)

    def list_articles(self) -> list[dict]:
        return self.storage.list_articles()

    def update_article(self, article_id: str, updates: dict) -> dict | None:
        updates["updated_at"] = utcnow_iso()
        return self.storage.update_article(article_id, updates)