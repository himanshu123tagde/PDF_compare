from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    APP_NAME: str = os.getenv("APP_NAME", "Scraper Service")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    )
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "pdf_compare")
    MONGODB_COLLECTION_NAME: str = os.getenv("MONGODB_COLLECTION_NAME", "pdf_compare")
    MIN_CONTENT_LENGTH: int = int(os.getenv("MIN_CONTENT_LENGTH", "200"))
    BATCH_MAX_URLS: int = int(os.getenv("BATCH_MAX_URLS", "50"))
    BATCH_MAX_CONCURRENT: int = int(os.getenv("BATCH_MAX_CONCURRENT", "2"))
    WORKFLOW_MIN_URLS: int = int(os.getenv("WORKFLOW_MIN_URLS", "1"))
    WORKFLOW_MAX_URLS: int = int(os.getenv("WORKFLOW_MAX_URLS", "3"))
    UPLOAD_MAX_SIZE_MB: int = int(os.getenv("UPLOAD_MAX_SIZE_MB", "20"))
    UPLOAD_ALLOWED_EXTENSIONS: str = os.getenv(
        "UPLOAD_ALLOWED_EXTENSIONS", ".pdf,.docx,.doc,.txt"
    )
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
    OPENROUTER_BASE_URL: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    OPENROUTER_MAX_TOKENS: int = int(os.getenv("OPENROUTER_MAX_TOKENS", "8000"))
    OPENROUTER_TEMPERATURE: float = float(os.getenv("OPENROUTER_TEMPERATURE", "0.1"))
    OPENROUTER_TIMEOUT: int = int(os.getenv("OPENROUTER_TIMEOUT", "120"))
    COMPARISON_MAX_CONCURRENT: int = int(os.getenv("COMPARISON_MAX_CONCURRENT", "1"))
    OPENROUTER_APP_TITLE: str = os.getenv("OPENROUTER_APP_TITLE", "PDF Compare Compliance")


settings = Settings()
