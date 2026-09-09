from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Fact Knowledge Layer"
    database_url: str = "postgresql+asyncpg://facts:facts@localhost:5433/facts"
    upload_dir: Path = Path("./data/uploads")
    max_upload_bytes: int = 100 * 1024 * 1024
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    worker_poll_seconds: float = 1.0
    worker_lease_seconds: int = 300
    parser_version: str = "pymupdf-1"
    embedding_dimensions: int = Field(default=384, ge=1)
    llm_provider: str = "openrouter"
    openrouter_api_key: str | None = None
    openrouter_text_model: str | None = None
    openrouter_embedding_model: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str | None = None
    openrouter_app_name: str = "Facts Store"
    fact_extraction_concurrency: int = Field(default=3, ge=1, le=20)
    fact_extraction_page_batch_size: int = Field(default=4, ge=1, le=20)
    facts_per_page_limit: int = Field(default=8, ge=1, le=100)
    embedding_batch_size: int = Field(default=90, ge=1, le=100)
    embedding_items_per_minute: int = Field(default=90, ge=0)
    candidates_per_fact: int = Field(default=8, ge=1, le=50)
    min_candidate_similarity: float = Field(default=0.55, ge=0, le=1)
    min_llm_relationship_similarity: float = Field(default=0.82, ge=0, le=1)
    max_llm_relationships_per_document: int = Field(default=12, ge=0, le=1000)
    openrouter_timeout_ms: int = Field(default=60_000, ge=1_000)
    openrouter_retry_attempts: int = Field(default=3, ge=1, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
