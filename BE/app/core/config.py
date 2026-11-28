"""Application settings, read from environment / BE/.env (never hardcoded)."""
from functools import lru_cache
from typing import Literal
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str
    # connection pool per process; the sharded test runner lowers it (Supabase's session pooler caps clients)
    db_pool_size: int = 3
    db_max_overflow: int = 2
    # AR-02 (audit 2026-11-27): how long a statement may wait for a row lock, in milliseconds (0 = wait for ever, as before).
    # The pool is tiny; a request that waits indefinitely for a lock held by a slow one (an outbound payment call, a stuck
    # client) takes a connection with it until nothing is left. 20 s is longer than any outbound call made under a lock
    # (15 s), so only a lock that is really stuck is given up on; the caller gets 409 RESOURCE_BUSY and may retry.
    db_lock_timeout_ms: int = 20000
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 7
    # FR-01: temporary lock after 5 wrong passwords. Lock length is an assumption.
    max_failed_logins: int = 5
    # 2026-11-27: Firebase phone sign-in as the proof of a phone number (integrations/firebase_auth.py). The project id of
    # the Firebase project whose web app runs the phone flow; empty = the Firebase routes answer 503 FIREBASE_NOT_CONFIGURED.
    firebase_project_id: str | None = None
    firebase_phone_max_age_seconds: int = 600      # how old the SMS sign-in behind the ID token may be
    # 2026-11-26: bell reminders to add / verify the phone number at sign-in and on a phone change (services/phone_reminders.py)
    phone_reminders_enabled: bool = True
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
    # PUBLIC bucket of catalog media (migration 0030): the workshop's photos of papers, pens, inks and template previews.
    # World-readable by address, written only by this server. It must NOT be the bucket of customer uploads above.
    catalog_media_bucket: str = "catalog-media"
    upload_url_ttl_seconds: int = 7200
    # ---- online payments (VNPay, MoMo) ---------------------------------------------------------------------
    # mock    = simulated payments only (default; tests and local work). No call leaves the server.
    # sandbox = the gateways' TEST environments: real API calls, test money.
    # live    = production: REAL MONEY. Needs production credentials; switch only on the project owner's say.
    payment_mode: Literal["mock", "sandbox", "live"] = "mock"
    # D01 (audit 2026-11-27): a payment that moves no real money (the MOCK gateway, a gateway's SANDBOX) confirms an order exactly
    # like a real one: the customer presses "paid" (mock) or uses a published test card (sandbox) and the workshop writes and
    # ships for nothing. Off by default, so a deployment that takes real orders refuses them; a demo / test environment sets
    # ALLOW_TEST_PAYMENTS=true. payOS is never a test payment (real bank transfers), whatever this says.
    allow_test_payments: bool = False
    # Where the gateways send the customer back after paying (a page of the web app). Display only: the order is
    # only ever updated by the gateway's IPN, never by this redirect.
    payment_return_url: str = "http://localhost:5173/payment/result"
    # Address of the web app, for links in e-mails (password reset). Empty: the origin of PAYMENT_RETURN_URL.
    public_web_url: str | None = None
    # U8: page of the web app that shows GET /api/v1/verify/{code}; the certificate card's QR code points to {url}/{code}
    public_verify_url: str = "http://localhost:5173/verify"
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
    # ---- carrier (GHN is the only one) ---------------------------------------------------------------------------------
    # mock    = simulated carrier (default). sandbox = GHN's TEST environment. live = production waybills.
    carrier_mode: Literal["mock", "sandbox", "live"] = "mock"
    # Shared secret GHN's callback carries (`?key=...` or the `X-Webhook-Secret` header); GHN does not sign its webhook.
    carrier_webhook_secret: str | None = None
    ghn_token: str | None = None
    ghn_shop_id: str | None = None
    # The pick-up address is the shop's own address registered with GHN (Developer Portal / `shop` API): nothing to set here.
    ghn_base_url: str = "https://dev-online-gateway.ghn.vn/shiip/public-api"
    # ---- e-mail (alerts to staff). Without SMTP_HOST the console mailer only logs. Credentials belong in BE/.env, never in git.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    smtp_reply_to: str | None = None          # e.g. the project's mailbox; replies to notification mails go there
    smtp_html: bool = True                    # add the HTML part with the logo (false: plain text only)
    smtp_timeout_seconds: float = 10.0
    # ---- SMS (Phase 5e, FR-53 OTP). mock = nothing leaves the server (default; tests and local work). esms = eSMS.vn
    # (integrations/sms.py). OTP rules are assumptions approved with the 5e plan (2026-11-11).
    sms_mode: Literal["mock", "esms", "speedsms", "speedsms2fa"] = "mock"
    # SpeedSMS (personal account, no business licence). No sandbox: speedsms mode sends REAL, paid SMS.
    # sms_type 4 = SpeedSMS's default Brandname (Verify / Notify); 2 = random number; 3 = own Brandname and 5 = their
    # Android app both need SPEEDSMS_SENDER (the Brandname / the device id).
    speedsms_access_token: str | None = None
    speedsms_sms_type: int = 4                # 2, 3, 4 or 5; an int (env values are strings: Literal[2, 3, 4, 5] refused "4")
    speedsms_sender: str | None = None
    speedsms_base_url: str = "https://api.speedsms.vn/index.php"
    # SMS_MODE=speedsms2fa (2026-11-26): codes through a SpeedSMS 2FA app (brandname "Verify", no own sender needed);
    # the App ID shown at connect.speedsms.vn > Verification. Uses SPEEDSMS_ACCESS_TOKEN too.
    speedsms_2fa_app_id: str | None = None
    sms_timeout_seconds: float = 10.0

    @field_validator("speedsms_sms_type")
    @classmethod
    def _speedsms_type(cls, v: int) -> int:
        if v not in (2, 3, 4, 5):
            raise ValueError("SPEEDSMS_SMS_TYPE must be 2, 3, 4 or 5")
        return v

    esms_api_key: str | None = None
    esms_secret_key: str | None = None
    esms_brandname: str | None = None     # registered with the carriers through eSMS; the OTP texts must match its templates
    # true = eSMS answers but delivers nothing and charges nothing. Real SMS (false) only on the project owner's say.
    esms_sandbox: bool = True
    esms_sms_type: int = 2                # 2 = Brandname CSKH (customer care / OTP)
    esms_base_url: str = "https://rest.esms.vn/MainService.svc/json"
    otp_ttl_seconds: int = 300           # a code lives 5 minutes
    otp_max_attempts: int = 5            # wrong guesses per code, then it is burned
    otp_resend_seconds: int = 60         # wait between two codes to the same number
    otp_daily_limit: int = 5             # codes per number in any 24 hours
    # ---- background jobs (Phase 5a): quotation expiry, deposit deadline, acceptance reminder / auto-accept, e-mail retry,
    # BR-23 purge. Off by default (local runs, tests); set BACKGROUND_JOBS_ENABLED=true on the one deployed instance.
    background_jobs_enabled: bool = False
    background_jobs_interval_seconds: int = 600
    # ---- robot motion (Phase: FAIRINO FR3 integration) ----------------------------------------------------
    # When true, a job's simulation result is only accepted if the calibration carries the measured motion block
    # (`frame_transform.schema == "vhrs-motion/1"`) AND the server's own deterministic validation passes. Turn this on for
    # any station that drives a real robot. Left off, old clients that only report `passed` keep working.
    motion_validation_required: bool = False
    # Google sign-in: OAuth *Web* client id(s) from Google Cloud Console, comma separated. Empty = the endpoint answers 503.
    # Env name GOOGLE_CLIENT (what Render uses); GOOGLE_CLIENT_ID is still accepted.
    google_client_id: str | None = Field(default=None, validation_alias=AliasChoices("GOOGLE_CLIENT", "GOOGLE_CLIENT_ID"))
    # ---- signed production packages (upgrade U1, core/production_signing.py) --------------------------------------
    # PRODUCTION_SIGNING_KEY: base64 Ed25519 private key (scripts/production_key.py new). Without it no production
    # snapshot can be issued and scheduling answers 503. PRODUCTION_VERIFY_KEYS: JSON {key_id: public key} of OLDER keys
    # still accepted while their jobs finish (the current key's public half is always in the ring).
    production_signing_key: str | None = None
    production_signing_key_id: str = "k1"
    production_verify_keys: str | None = None
    # ---- AI assistant of the studio (upgrade U5, Q1: several providers, automatic failover) ------------------------
    # A provider is used only when its key is set; the keys stay in the environment (BE/.env, Render), never in the DB.
    # LLM_PROVIDER_ORDER: the order they are tried in. Without any key the assistant answers 503 AI_UNAVAILABLE and the
    # studio still works through its forms. LLM_PRICES: JSON {model: [USD per 1M input tokens, USD per 1M output tokens]};
    # a model without a price gets cost NULL (never a guessed figure) and then only the call caps apply.
    llm_provider_order: str = "anthropic,openai,gemini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str | None = None
    openai_model: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    llm_timeout_seconds: float = 30.0
    # AI-02 (audit 2026-11-27): a turn of the assistant keeps one database connection and the order's row lock while it waits
    # for the model. With a pool of five, a handful of chats at once left nothing for payments or the workshop. At most this
    # many turns run at the same time in this process (the others get 503 AI_BUSY and retry), and one turn stops asking the
    # model for more once it has run this long.
    ai_max_concurrent_turns: int = 2
    ai_turn_deadline_seconds: float = 90.0
    llm_prices: str | None = None
    # V2 Phase E2b: who reads the customer's photo of an OT-1 letter (page transcript for the region text hints). Only
    # providers that can read images and have a key are used, in this order; the on / off switch and the daily page cap
    # are system settings (htr_enabled, htr_daily_pages). Owner 2026-11-19: Gemini first, Claude when Gemini fails.
    htr_provider_order: str = "gemini,anthropic"
    htr_timeout_seconds: float = 90.0

    @property
    def production_key_ring(self) -> dict[str, str]:
        from app.core import production_signing as ps
        ring = ps.parse_key_ring(self.production_verify_keys)
        if self.production_signing_key:
            ring[self.production_signing_key_id] = ps.public_key_of(self.production_signing_key)
        return ring

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
