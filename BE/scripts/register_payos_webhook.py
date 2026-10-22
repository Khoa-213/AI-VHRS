"""Register this API's payOS webhook address with payOS (run once per environment, and again whenever the address changes).

    .venv/bin/python scripts/register_payos_webhook.py            # uses PUBLIC_BASE_URL and the PAYOS_* keys from the environment

payOS first POSTs a test message to the address; our endpoint answers it with 200, so the server must already be running the
code that has POST /api/v1/webhooks/payments/payos. Prints payOS's answer (never the keys).
"""
from __future__ import annotations

import sys

from app.core.config import get_settings
from app.integrations import payment_gateway as gw


def main() -> int:
    s = get_settings()
    if not s.public_base_url:
        print("PUBLIC_BASE_URL is not set.")
        return 2
    adapter = gw.real_adapter("PAYOS", strict=False)
    if adapter is None:
        print("PAYOS_CLIENT_ID / PAYOS_API_KEY / PAYOS_CHECKSUM_KEY are not all set.")
        return 2
    url = f"{s.public_base_url.rstrip('/')}/api/v1/webhooks/payments/payos"
    out = adapter.confirm_webhook(url)
    print("webhook address:", url)
    print("payOS answered: code=%s desc=%s" % (out.get("code"), out.get("desc")))
    return 0 if out.get("code") == "00" else 1


if __name__ == "__main__":
    sys.exit(main())
