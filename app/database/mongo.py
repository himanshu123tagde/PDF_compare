import logging

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database

from app.config import settings

logger = logging.getLogger(__name__)

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        if not settings.MONGODB_URI:
            raise RuntimeError("MONGODB_URI is not configured.")
        _client = MongoClient(settings.MONGODB_URI)
    return _client


def get_database() -> Database:
    return get_client()[settings.MONGODB_DB_NAME]


def get_app_collection():
    return get_database()[settings.MONGODB_COLLECTION_NAME]


def get_uploads_bucket_name() -> str:
    return f"{settings.MONGODB_COLLECTION_NAME}_uploads"


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def init_database() -> None:
    collection = get_app_collection()
    collection.create_index(
        [("entity_type", ASCENDING), ("id", ASCENDING)],
        unique=True,
        name="entity_type_id_unique",
    )
    collection.create_index(
        [("entity_type", ASCENDING), ("created_at", DESCENDING)],
        name="entity_type_created_at",
    )
    collection.create_index(
        [("entity_type", ASCENDING), ("workflow_id", ASCENDING)],
        name="entity_type_workflow_id",
    )

    uploads_files = f"{get_uploads_bucket_name()}.files"
    get_database()[uploads_files].create_index(
        [("metadata.document_id", ASCENDING)],
        name="upload_document_id",
    )

    logger.info(
        "MongoDB ready: database=%s collection=%s",
        settings.MONGODB_DB_NAME,
        settings.MONGODB_COLLECTION_NAME,
    )
