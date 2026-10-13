"""Client address resolution shared by rate limiting and audit logging."""
import ipaddress

from fastapi import Request

from app.core.config import get_settings


def resolve_client_ip(request: Request) -> str | None:
    """Literal peer IP, or the address our single trusted reverse proxy appended to X-Forwarded-For.

    The proxy adds the address it saw as the LAST entry, so earlier entries are client-supplied and
    must be ignored. Enable TRUST_PROXY_HEADERS only when exactly one proxy sits in front of the API
    and the API cannot be reached any other way.
    """
    host = request.client.host if request.client else None
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            host = forwarded.split(",")[-1].strip()
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None
