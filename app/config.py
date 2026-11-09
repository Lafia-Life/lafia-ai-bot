import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI
from pydantic import BaseModel, Field


load_dotenv()


def _resolve_openai_key() -> Optional[str]:
    return (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("DEEPSEEK_KEY")
        or None
    )


def _resolve_openai_base_url() -> Optional[str]:
    return (
        os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("DEEPSEEK_API_BASE")
        or None
    )


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    openai_api_key: Optional[str] = Field(default_factory=_resolve_openai_key)
    openai_base_url: Optional[str] = Field(default_factory=_resolve_openai_base_url)
    llm_provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai-compatible"))
    chat_model: str = Field(
        default_factory=lambda: os.getenv("LLM_MODEL") or os.getenv("CHAT_MODEL") or "gpt-4o-mini"
    )
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
    scraper_enable_http2: bool = Field(default_factory=lambda: _env_flag("SCRAPER_HTTP2", False))
    who_sync_on_startup: bool = Field(default_factory=lambda: _env_flag("WHO_SYNC_ON_STARTUP", True))
    
    # Supabase authentication (placeholders are replaced in production)
    supabase_url: Optional[str] = Field(default_factory=lambda: os.getenv("SUPABASE_URL"))
    supabase_anon_key: Optional[str] = Field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY"))
    supabase_service_role_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    auth_required: bool = Field(default_factory=lambda: _env_flag("AUTH_REQUIRED", False))
    auth_cookie_secure: bool = Field(default_factory=lambda: _env_flag("AUTH_COOKIE_SECURE", False))

    # SMS Configuration for Africa's Talking (Uganda)
    africas_talking_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("AFRICAS_TALKING_API_KEY"))
    africas_talking_username: str = Field(default_factory=lambda: os.getenv("AFRICAS_TALKING_USERNAME", "sandbox"))
    sms_webhook_secret: Optional[str] = Field(default_factory=lambda: os.getenv("SMS_WEBHOOK_SECRET"))

    class Config:
        arbitrary_types_allowed = True


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    backend = settings.embedding_backend.lower()
    if backend not in {"openai", "local", "auto", "hash"}:
        backend = "auto"
    if backend == "auto":
        backend = "hash"
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


def get_openai_async_client(settings: Optional[Settings] = None) -> AsyncOpenAI:
    current = settings or get_settings()
    kwargs = {}
    if current.openai_api_key:
        kwargs["api_key"] = current.openai_api_key
    if current.openai_base_url:
        kwargs["base_url"] = current.openai_base_url.rstrip("/")
    return AsyncOpenAI(**kwargs)
