import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.mongo import close_client, get_database, init_database
from app.routers.admin_scraper import router as scraper_router
from app.routers.workflows import router as workflows_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.MONGODB_URI:
        raise RuntimeError("MONGODB_URI is required. Set it in your .env file.")

    init_database()
    get_database().command("ping")
    logger.info("Connected to MongoDB database: %s collection: %s", settings.MONGODB_DB_NAME, settings.MONGODB_COLLECTION_NAME)
    yield
    close_client()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("CORS allowed origins: %s", _cors_origins)


@app.get("/")
def root():
    return {
        "message": "Scraper service is running",
        "database": settings.MONGODB_DB_NAME,
        "collection": settings.MONGODB_COLLECTION_NAME,
    }


app.include_router(scraper_router)
app.include_router(workflows_router)
