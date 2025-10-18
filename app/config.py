import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


load_dotenv()


def _resolve_openai_key() -> Optional[str]:
    return (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("DEEPSEEK_KEY")
        or None
    )


def _resolve_openai_base_url() -> Optional[str]:
    return (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("DEEPSEEK_API_BASE")
        or None
    )


class Settings(BaseModel):
    openai_api_key: Optional[str] = Field(default_factory=_resolve_openai_key)
    openai_base_url: Optional[str] = Field(default_factory=_resolve_openai_base_url)
    chat_model: str = Field(default_factory=lambda: os.getenv("CHAT_MODEL", "gpt-4o-mini"))
    embedding_backend: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_BACKEND", "auto")
    )
    embedding_model: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    )
    local_embedding_model: str = Field(
        default_factory=lambda: os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    )
    chunk_size: int = Field(default=800)
    chunk_overlap: int = Field(default=200)
    chroma_path: Path = Field(default_factory=lambda: Path("storage") / "chroma")
    uploads_path: Path = Field(default_factory=lambda: Path("storage") / "uploads")
    scraper_user_agent: str = Field(
        default_factory=lambda: os.getenv(
            "SCRAPER_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
    )
    scraper_timeout: float = Field(default_factory=lambda: float(os.getenv("SCRAPER_TIMEOUT", "20")))
    scraper_proxy_url: Optional[str] = Field(default_factory=lambda: os.getenv("SCRAPER_PROXY_URL"))

    class Config:
        arbitrary_types_allowed = True


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    backend = settings.embedding_backend.lower()
    if backend not in {"openai", "local", "auto"}:
        backend = "auto"
    if backend == "auto":
        backend = "openai" if settings.openai_api_key else "local"
    settings.embedding_backend = backend
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    return settings


def get_openai_api_key() -> Optional[str]:
    return get_settings().openai_api_key or None


def get_openai_client(settings: Optional[Settings] = None) -> OpenAI:
    current = settings or get_settings()
    kwargs = {}
    if current.openai_api_key:
        kwargs["api_key"] = current.openai_api_key
    if current.openai_base_url:
        kwargs["base_url"] = current.openai_base_url.rstrip("/")
    return OpenAI(**kwargs)
