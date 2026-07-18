"""Authentication and rate limiting.

Two credentials are accepted, for two different callers:

- ``X-API-Key`` — machine clients (CI, scripts). Unchanged behaviour.
- a signed session cookie — the web UI. A static API key cannot be shipped to a
  browser: it would be readable by every user and by any XSS on the page. The UI
  exchanges nothing at all for a short-lived, ``HttpOnly`` cookie that JavaScript
  cannot read, and the browser attaches it to the SSE request automatically.

The cookie is signed with ``settings.SECRET_KEY`` and carries its own expiry.
"""

import hashlib
import hmac
import logging
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import Cookie, HTTPException, Security
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Shared limiter for @limiter.limit(...) decorators on endpoints
limiter = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ENABLED)

SESSION_COOKIE_NAME = "ai_devops_session"
CSRF_COOKIE_NAME = "ai_devops_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def _sign(payload: str) -> str:
    """Return the HMAC-SHA256 signature of a payload, base64url encoded."""
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_session_token(subject: str = "web-ui", ttl_seconds: int | None = None) -> str:
    """Mint a signed, expiring session token.

    Format is ``<subject>.<expiry>.<signature>``. Self-contained so verifying it
    needs no server-side store — which also means it cannot be revoked before
    expiry, hence the short default TTL.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.SESSION_TTL_SECONDS
    expires_at = int(time.time()) + ttl
    payload = f"{urlsafe_b64encode(subject.encode()).decode().rstrip('=')}.{expires_at}"
    return f"{payload}.{_sign(payload)}"


def verify_session_token(token: str) -> bool:
    """Check a session token's signature and expiry.

    Returns False rather than raising: callers decide whether a bad token is a
    401 or a fall-through to another credential.
    """
    try:
        subject_b64, expires_raw, signature = token.rsplit(".", 2)
    except ValueError:
        return False

    payload = f"{subject_b64}.{expires_raw}"
    # compare_digest, not ==, so a wrong signature cannot be recovered byte by
    # byte from response timing.
    if not hmac.compare_digest(signature, _sign(payload)):
        return False

    try:
        expires_at = int(expires_raw)
    except ValueError:
        return False

    return time.time() < expires_at


def issue_csrf_token() -> str:
    """Mint a random CSRF token to pair with a session cookie."""
    return secrets.token_urlsafe(32)


def _api_key_valid(api_key: str | None) -> bool:
    """Whether the supplied API key matches the configured one."""
    if not api_key:
        return False
    return hmac.compare_digest(api_key, settings.API_KEY)


async def require_auth(
    api_key: str = Security(api_key_header),
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> None:
    """Accept either a valid API key or a valid session cookie.

    Auth is disabled when settings.API_KEY is unset (local demo mode). In
    production that combination is refused at startup by main.create_app(), so
    this cannot silently leave production open.
    """
    if not settings.API_KEY:
        return

    if _api_key_valid(api_key):
        return

    if session and verify_session_token(session):
        return

    raise HTTPException(status_code=401, detail="Invalid or missing credentials")


# Backwards-compatible alias: require_api_key was the original name and is still
# what several routers import.
require_api_key = require_auth


def _decode_subject(token: str) -> str | None:
    """Extract the subject from a token without verifying it. Diagnostics only."""
    try:
        subject_b64 = token.rsplit(".", 2)[0]
        padding = "=" * (-len(subject_b64) % 4)
        return urlsafe_b64decode(subject_b64 + padding).decode("utf-8")
    except Exception:
        return None
