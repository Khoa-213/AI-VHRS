"""Client address resolution shared by rate limiting and audit logging."""
import ipaddress

from fastapi import Request

from app.core.config import get_settings


def resolve_client_ip(request: Request) -> str | None:
    """Literal peer IP, or the first X-Forwarded-For hop when we run behind a trusted proxy.

    Only enable TRUST_PROXY_HEADERS when the API is reachable exclusively through that proxy,
    otherwise clients could spoof the header to dodge rate limits.
    """
    host = request.client.host if request.client else None
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            host = forwarded.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None
