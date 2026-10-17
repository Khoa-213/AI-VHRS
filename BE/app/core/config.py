"""Application settings, read from environment / BE/.env (never hardcoded)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 7
    reset_token_ttl_min: int = 30
    # FR-01: temporary lock after 5 wrong passwords. Lock length is an assumption.
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    cors_origins: list[str] = ["http://localhost:5173"]
    # Optional regex for dynamic origins such as Vercel preview URLs:
    # https://ai-vhrs-fe-[a-z0-9-]+-<team>\.vercel\.app . Keep it as narrow as possible.
    cors_origin_regex: str | None = None
    # Swagger UI / ReDoc / openapi.json. Turn off in production.
    enable_docs: bool = True
    rate_limit_enabled: bool = True
    # Trust X-Forwarded-For / -Proto only when the API sits behind our own reverse proxy.
    trust_proxy_headers: bool = False
    # Object storage for customer uploads (Supabase Storage). Server-side only: the service key
    # must never reach a client. Leave empty to disable uploads (endpoints answer 503).
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    storage_bucket: str = "order-inputs"
    upload_url_ttl_seconds: int = 7200
    # Google sign-in: OAuth *Web* client id(s) from Google Cloud Console, comma separated. Empty = the endpoint answers 503.
    google_client_id: str | None = None

    @property
    def google_client_ids(self) -> list[str]:
        return [c.strip() for c in (self.google_client_id or "").split(",") if c.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """psycopg3 driver URL derived from the plain postgresql:// URL."""
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
