"""Session exchange for browser clients.

The web UI cannot hold the API key: anything JavaScript can read is readable by
every user of the page and by any XSS on it. Instead the key is exchanged once,
server side, for a short-lived signed cookie that JavaScript cannot read and the
browser attaches automatically — including to the SSE stream.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Response

from ai_devops_assistant.api.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    issue_csrf_token,
    issue_session_token,
    limiter,
)
from ai_devops_assistant.api.schemas import SessionRequest, SessionResponse
from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session", response_model=SessionResponse)
@limiter.limit("10/minute")
async def create_session(
    request: Request,
    response: Response,
    session_request: SessionRequest,
) -> SessionResponse:
    """Exchange an API key for a short-lived session cookie.

    Rate limited: this endpoint takes a credential, so it is the natural place to
    brute-force one.

    Args:
        request: Raw HTTP request (required by the rate limiter)
        response: Response, used to set the cookies
        session_request: Carries the API key

    Returns:
        SessionResponse: the CSRF token and the session lifetime
    """
    # When no API key is configured the deployment is in local demo mode and all
    # routes are already open, so issuing a session freely matches that posture.
    if settings.API_KEY:
        import hmac

        supplied = session_request.api_key or ""
        if not hmac.compare_digest(supplied, settings.API_KEY):
            logger.warning("Rejected session request with an invalid API key")
            raise HTTPException(status_code=401, detail="Invalid API key")

    token = issue_session_token()
    csrf_token = issue_csrf_token()

    # HttpOnly: unreadable from JavaScript, so an XSS cannot exfiltrate it.
    # SameSite=strict: not sent on cross-site requests, which is the primary CSRF
    # defence; the CSRF token below is defence in depth for the streaming POST.
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    # Readable by JavaScript on purpose: the client must echo it back in a header,
    # which an attacker on another origin cannot do.
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=False,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )

    return SessionResponse(csrf_token=csrf_token, expires_in=settings.SESSION_TTL_SECONDS)


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    """Clear the session cookies.

    The token stays valid until it expires — it is self-contained and not tracked
    server side — so this ends the browser's session, not the token's life.
    """
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return {"ok": True}
