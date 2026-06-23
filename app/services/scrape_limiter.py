import asyncio

from app.config import settings

scrape_semaphore = asyncio.Semaphore(settings.BATCH_MAX_CONCURRENT)
