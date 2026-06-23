import asyncio

from app.config import settings

comparison_semaphore = asyncio.Semaphore(settings.COMPARISON_MAX_CONCURRENT)
