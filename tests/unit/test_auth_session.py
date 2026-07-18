"""Unit tests for browser session authentication.

The security property under test is that the web UI never needs to hold the API
key: it exchanges one for a short-lived, signed, HttpOnly cookie.
"""

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from ai_devops_assistant.api.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    issue_csrf_token,
    issue_session_token,
    require_auth,
    verify_session_token,
)
from ai_devops_assistant.config.settings import settings


class TestSessionToken:
    """Signing and expiry of the session token."""

    def test_issued_token_verifies(self):
        assert verify_session_token(issue_session_token()) is True

    def test_tampered_payload_is_rejected(self):
        token = issue_session_token()
        subject, expires, signature = token.rsplit(".", 2)
        # Extend the expiry without re-signing — the classic forgery attempt.
        forged = f"{subject}.{int(expires) + 100_000}.{signature}"
        assert verify_session_token(forged) is False

    def test_tampered_signature_is_rejected(self):
        token = issue_session_token()
        assert verify_session_token(token[:-4] + "AAAA") is False

    def test_expired_token_is_rejected(self):
        token = issue_session_token(ttl_seconds=-1)
        assert verify_session_token(token) is False

    def test_token_expiring_in_future_is_accepted(self):
        token = issue_session_token(ttl_seconds=60)
        assert verify_session_token(token) is True
        assert int(token.rsplit(".", 2)[1]) > int(time.time())

    def test_malformed_tokens_are_rejected_not_raised(self):
        for junk in ("", "abc", "a.b", "...", "a.b.c.d", "x.notanumber.sig"):
            assert verify_session_token(junk) is False, junk

    def test_token_signed_with_a_different_secret_is_rejected(self):
        token = issue_session_token()
        with patch.object(settings, "SECRET_KEY", "a-completely-different-secret"):
            assert verify_session_token(token) is False

    def test_tokens_are_not_predictable_across_secrets(self):
        with patch.object(settings, "SECRET_KEY", "secret-one"):
            first = issue_session_token(ttl_seconds=60)
        with patch.object(settings, "SECRET_KEY", "secret-two"):
            second = issue_session_token(ttl_seconds=60)
        assert first.rsplit(".", 1)[1] != second.rsplit(".", 1)[1]


class TestCsrfToken:
    def test_tokens_are_unique(self):
        assert issue_csrf_token() != issue_csrf_token()

    def test_token_has_meaningful_entropy(self):
        assert len(issue_csrf_token()) >= 32


class TestRequireAuth:
    """require_auth accepts an API key or a session cookie, and nothing else."""

    @pytest.mark.asyncio
    async def test_open_when_no_api_key_configured(self):
        with patch.object(settings, "API_KEY", None):
            await require_auth(api_key=None, session=None)  # must not raise

    @pytest.mark.asyncio
    async def test_valid_api_key_is_accepted(self):
        with patch.object(settings, "API_KEY", "correct-key"):
            await require_auth(api_key="correct-key", session=None)

    @pytest.mark.asyncio
    async def test_wrong_api_key_is_rejected(self):
        with patch.object(settings, "API_KEY", "correct-key"):
            with pytest.raises(HTTPException) as exc:
                await require_auth(api_key="wrong-key", session=None)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_credentials_are_rejected(self):
        with patch.object(settings, "API_KEY", "correct-key"):
            with pytest.raises(HTTPException) as exc:
                await require_auth(api_key=None, session=None)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_session_cookie_is_accepted_without_an_api_key(self):
        """This is the browser path: cookie only, no key in the request."""
        with patch.object(settings, "API_KEY", "correct-key"):
            token = issue_session_token()
            await require_auth(api_key=None, session=token)

    @pytest.mark.asyncio
    async def test_expired_session_cookie_is_rejected(self):
        with patch.object(settings, "API_KEY", "correct-key"):
            with pytest.raises(HTTPException):
                await require_auth(api_key=None, session=issue_session_token(ttl_seconds=-1))

    @pytest.mark.asyncio
    async def test_forged_session_cookie_is_rejected(self):
        with patch.object(settings, "API_KEY", "correct-key"):
            with pytest.raises(HTTPException):
                await require_auth(api_key=None, session="forged.9999999999.nope")


class TestSessionEndpoint:
    """POST /auth/session end to end."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from ai_devops_assistant.main import create_app

        return TestClient(create_app())

    def test_valid_key_sets_an_httponly_session_cookie(self, client):
        with patch.object(settings, "API_KEY", "correct-key"):
            resp = client.post("/auth/session", json={"api_key": "correct-key"})

        assert resp.status_code == 200
        cookie_header = resp.headers.get("set-cookie", "")
        assert SESSION_COOKIE_NAME in cookie_header
        assert "HttpOnly" in cookie_header, "session cookie must be unreadable from JS"
        assert "SameSite=strict" in cookie_header.lower().replace(
            "samesite=strict", "SameSite=strict"
        )

    def test_response_body_never_contains_the_session_token(self, client):
        """The token belongs in an HttpOnly cookie, never anywhere JS can read."""
        with patch.object(settings, "API_KEY", "correct-key"):
            resp = client.post("/auth/session", json={"api_key": "correct-key"})

        body = resp.json()
        assert "csrf_token" in body
        assert "expires_in" in body
        for value in body.values():
            assert SESSION_COOKIE_NAME not in str(value)
        # And the API key must not be echoed back either.
        assert "correct-key" not in resp.text

    def test_invalid_key_is_rejected_and_sets_no_cookie(self, client):
        with patch.object(settings, "API_KEY", "correct-key"):
            resp = client.post("/auth/session", json={"api_key": "wrong-key"})

        assert resp.status_code == 401
        assert SESSION_COOKIE_NAME not in resp.headers.get("set-cookie", "")

    def test_csrf_cookie_is_readable_by_javascript(self, client):
        """Deliberate: the client must echo it back in a header."""
        with patch.object(settings, "API_KEY", "correct-key"):
            resp = client.post("/auth/session", json={"api_key": "correct-key"})

        csrf_cookie = [c for c in resp.headers.get_list("set-cookie") if CSRF_COOKIE_NAME in c]
        assert csrf_cookie, "CSRF cookie should be set"
        assert "HttpOnly" not in csrf_cookie[0]

    def test_issued_cookie_authenticates_a_subsequent_request(self, client):
        """The whole point: cookie alone gets you through, no API key sent.

        SESSION_COOKIE_SECURE is disabled here only because TestClient speaks
        plain HTTP and will not return a Secure cookie over it — see
        test_secure_cookie_is_not_sent_over_plain_http for that behaviour.
        """
        with (
            patch.object(settings, "API_KEY", "correct-key"),
            patch.object(settings, "SESSION_COOKIE_SECURE", False),
        ):
            client.post("/auth/session", json={"api_key": "correct-key"})
            # TestClient retains cookies; no X-API-Key header on this call.
            resp = client.get("/chat/sessions/does-not-exist")

        assert resp.status_code != 401, "session cookie should have authenticated this"

    def test_secure_cookie_is_not_sent_over_plain_http(self, client):
        """Secure cookies are withheld on http, so an http deployment must opt out.

        Documents why SESSION_COOKIE_SECURE exists: with it left on, a local HTTP
        deployment authenticates once and then silently 401s on every request.
        """
        with (
            patch.object(settings, "API_KEY", "correct-key"),
            patch.object(settings, "SESSION_COOKIE_SECURE", True),
        ):
            client.post("/auth/session", json={"api_key": "correct-key"})
            resp = client.get("/chat/sessions/does-not-exist")

        assert resp.status_code == 401

    def test_cookie_is_marked_secure_by_default(self, client):
        with patch.object(settings, "API_KEY", "correct-key"):
            resp = client.post("/auth/session", json={"api_key": "correct-key"})

        session_cookie = [
            c for c in resp.headers.get_list("set-cookie") if SESSION_COOKIE_NAME in c
        ][0]
        assert "Secure" in session_cookie

    def test_logout_clears_the_cookies(self, client):
        with patch.object(settings, "API_KEY", "correct-key"):
            client.post("/auth/session", json={"api_key": "correct-key"})
            resp = client.post("/auth/logout")

        assert resp.status_code == 200
        assert 'ai_devops_session=""' in resp.headers.get(
            "set-cookie", ""
        ) or "Max-Age=0" in resp.headers.get("set-cookie", "")
