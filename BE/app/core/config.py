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
    rate_limit_enabled: bool = True
    # Trust X-Forwarded-For / -Proto only when the API sits behind our own reverse proxy.
    trust_proxy_headers: bool = False

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
