import logging
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ExtractUrlRequest,
    UpdateArticleRequest,
    BatchExtractRequest,
    BatchJobResponse,
)
from app.services.scraper_service import ScraperService
from app.services.batch_service import BatchScraperService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/scraper", tags=["Scraper"])

scraper_service = ScraperService()
batch_service = BatchScraperService(scraper_service)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/extract")
async def extract_url(payload: ExtractUrlRequest):
    try:
        result = await scraper_service.scrape_url(str(payload.url))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-batch", response_model=BatchJobResponse, status_code=202)
async def extract_batch(payload: BatchExtractRequest):
    try:
        job = batch_service.create_job([str(url) for url in payload.urls])
        return job
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Batch job creation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batch/{job_id}", response_model=BatchJobResponse)
def get_batch_job(job_id: str):
    job = batch_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found.")
    return job


@router.get("/articles")
def list_articles():
    items = scraper_service.list_articles()
    return {"items": items, "total": len(items)}


@router.get("/articles/{article_id}")
def get_article(article_id: str):
    article = scraper_service.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    return article


@router.patch("/articles/{article_id}")
def update_article(article_id: str, payload: UpdateArticleRequest):
    updates = payload.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    article = scraper_service.update_article(article_id, updates)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    return article