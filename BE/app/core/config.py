"""Application settings, read from environment / BE/.env (never hardcoded)."""
from functools import lru_cache
from typing import Literal
from pathlib import Path

from pydantic import AliasChoices, Field
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
    # ---- online payments (VNPay, MoMo) ---------------------------------------------------------------------
    # mock    = simulated payments only (default; tests and local work). No call leaves the server.
    # sandbox = the gateways' TEST environments: real API calls, test money.
    # live    = production: REAL MONEY. Needs production credentials; switch only on the project owner's say.
    payment_mode: Literal["mock", "sandbox", "live"] = "mock"
    # Where the gateways send the customer back after paying (a page of the web app). Display only: the order is
    # only ever updated by the gateway's IPN, never by this redirect.
    payment_return_url: str = "http://localhost:5173/payment/result"
    # Public base URL of this API (e.g. https://ai-vhrs-be.onrender.com); the gateways call back to {base}/api/v1/webhooks/...
    public_base_url: str | None = None
    payment_expire_minutes: int = 15
    vnpay_tmn_code: str | None = None
    vnpay_hash_secret: str | None = None
    vnpay_pay_url: str = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
    vnpay_api_url: str = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
    momo_partner_code: str | None = None
    momo_access_key: str | None = None
    momo_secret_key: str | None = None
    momo_endpoint: str = "https://test-payment.momo.vn"
    # payOS (VietQR bank transfer). It has no test environment: every payment is a real transfer, so it is available whenever
    # its three keys are set, whatever PAYMENT_MODE says (that switch only governs VNPay and MoMo).
    payos_client_id: str | None = None
    payos_api_key: str | None = None
    payos_checksum_key: str | None = None
    payos_base_url: str = "https://api-merchant.payos.vn"
    # ---- carriers (GHN, GHTK) --------------------------------------------------------------------------------------
    # mock    = simulated carriers (default). sandbox = the carriers' TEST environments. live = production waybills.
    carrier_mode: Literal["mock", "sandbox", "live"] = "mock"
    # Shared secret the carriers put in the callback address (`?key=...`); neither GHN nor GHTK signs its webhook by default.
    carrier_webhook_secret: str | None = None
    ghn_token: str | None = None
    ghn_shop_id: str | None = None
    ghn_base_url: str = "https://dev-online-gateway.ghn.vn/shiip/public-api"
    ghn_from_district_id: int | None = None          # where the workshop ships from (GHN location ids)
    ghn_from_ward_code: str | None = None
    ghtk_token: str | None = None
    ghtk_client_source: str | None = None            # the shop / partner code
    ghtk_base_url: str = "https://services-staging.ghtklab.com"
    # The workshop's pick-up address (GHTK wants names; shown on labels).
    # ---- e-mail (alerts to staff). Without SMTP_HOST the console mailer only logs. Credentials belong in BE/.env, never in git.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 10.0
    # ---- robot motion (Phase: FAIRINO FR3 integration) ----------------------------------------------------
    # When true, a job's simulation result is only accepted if the calibration carries the measured motion block
    # (`frame_transform.schema == "vhrs-motion/1"`) AND the server's own deterministic validation passes. Turn this on for
    # any station that drives a real robot. Left off, old clients that only report `passed` keep working.
    motion_validation_required: bool = False
    workshop_name: str = "Xuong Net Viet"
    workshop_phone: str | None = None
    workshop_address: str | None = None
    workshop_province: str | None = None
    workshop_district: str | None = None
    workshop_ward: str | None = None
    # Google sign-in: OAuth *Web* client id(s) from Google Cloud Console, comma separated. Empty = the endpoint answers 503.
    # Env name GOOGLE_CLIENT (what Render uses); GOOGLE_CLIENT_ID is still accepted.
    google_client_id: str | None = Field(default=None, validation_alias=AliasChoices("GOOGLE_CLIENT", "GOOGLE_CLIENT_ID"))

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
