"""Integration tests for serving the web UI and the model picker endpoint.

Includes a static assertion that no frontend file uses innerHTML. That is the
security property the renderer is built on: LLM output becomes DOM text nodes,
never parsed markup, so there is no sanitiser to bypass.
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.main import create_app

STATIC_DIR = Path(__file__).resolve().parents[2] / "ai_devops_assistant" / "static"


@pytest.fixture
def client():
    return TestClient(create_app())


class TestStaticAssets:
    """The UI is served from /ui and does not shadow the API."""

    def test_index_is_served(self, client):
        resp = client.get("/ui/")
        assert resp.status_code == 200
        assert "AI DevOps Assistant" in resp.text

    def test_javascript_modules_are_served_with_a_js_content_type(self, client):
        """A wrong MIME type makes the browser refuse an ES module outright."""
        resp = client.get("/ui/js/app.js")
        assert resp.status_code == 200
        assert "javascript" in resp.headers["content-type"]

    def test_stylesheet_is_served(self, client):
        resp = client.get("/ui/css/app.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]

    def test_all_modules_referenced_by_the_app_are_reachable(self, client):
        for path in ("/ui/js/app.js", "/ui/js/sse.js", "/ui/js/render.js", "/ui/js/markdown.js"):
            assert client.get(path).status_code == 200, path

    def test_ui_does_not_shadow_api_routes(self, client):
        """Mounted at /ui precisely so it cannot swallow /chat or /health."""
        assert client.get("/health").status_code == 200
        paths = {r.path for r in client.app.routes if hasattr(r, "path")}
        assert "/chat" in paths

    def test_ui_can_be_disabled(self):
        with patch.object(settings, "ENABLE_WEB_UI", False):
            disabled = TestClient(create_app())
            assert disabled.get("/ui/").status_code == 404


class TestFrontendSecurityInvariants:
    """Static checks on the shipped JS. Cheap, and they fail loudly on regression."""

    def _js_files(self):
        return sorted(STATIC_DIR.glob("js/*.js"))

    @staticmethod
    def _strip_comments(source: str) -> str:
        """Remove // and /* */ comments.

        Needed because these modules discuss innerHTML in their own docs; the
        check is about executable code, not prose about it.
        """
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        return re.sub(r"//[^\n]*", "", source)

    def _js_code(self):
        """Yield (name, executable source) for each frontend module."""
        for path in self._js_files():
            yield path.name, self._strip_comments(path.read_text(encoding="utf-8"))

    def test_frontend_files_exist(self):
        assert self._js_files(), "no frontend modules found"

    def test_no_module_uses_innerhtml(self):
        """The renderer's guarantee: nothing is ever parsed as HTML."""
        offenders = [name for name, code in self._js_code() if "innerHTML" in code]
        assert offenders == [], f"innerHTML found in {offenders}"

    def test_no_module_uses_outerhtml_or_insertadjacenthtml(self):
        offenders = [
            name
            for name, code in self._js_code()
            if "outerHTML" in code or "insertAdjacentHTML" in code
        ]
        assert offenders == [], f"HTML-parsing sink found in {offenders}"

    def test_no_module_uses_eval_or_function_constructor(self):
        offenders = [
            name for name, code in self._js_code() if "eval(" in code or "new Function(" in code
        ]
        assert offenders == [], f"dynamic code execution found in {offenders}"

    def test_no_third_party_scripts_are_referenced(self):
        """The page must be self-contained: no CDN, no external origin.

        Checks the src/href attributes that actually cause a fetch, rather than
        grepping for "http://" — the inline SVG favicon legitimately contains the
        w3.org XML namespace URI, which is an identifier and not a request.
        """
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        fetched = re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', html)
        external = [
            url
            for url in fetched
            if url.startswith(("http://", "https://", "//")) and not url.startswith("data:")
        ]
        assert external == [], f"external resources referenced: {external}"

    def test_no_cdn_hosts_appear_anywhere_in_the_page(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        for marker in ("cdn.", "unpkg", "jsdelivr", "googleapis"):
            assert marker not in html, f"CDN reference {marker!r} in index.html"

    def test_no_api_key_is_embedded_in_the_frontend(self):
        """The browser authenticates by cookie; a key must never be shipped."""
        for path in [*self._js_files(), STATIC_DIR / "index.html"]:
            source = path.read_text(encoding="utf-8").lower()
            assert "x-api-key" not in source, f"API key header referenced in {path.name}"


class TestModelsEndpoint:
    def test_returns_models_and_a_default(self, client):
        service = AsyncMock()
        service.list_models = AsyncMock(return_value=["llama3", "mistral"])
        with patch(
            "ai_devops_assistant.services.llm_service.get_llm_service",
            new=AsyncMock(return_value=service),
        ):
            resp = client.get("/models")

        assert resp.status_code == 200
        body = resp.json()
        assert "llama3" in body["models"]
        assert body["default"]

    def test_degrades_to_the_default_when_the_provider_is_unreachable(self, client):
        """A dead provider must not stop the user chatting."""
        with patch(
            "ai_devops_assistant.services.llm_service.get_llm_service",
            new=AsyncMock(side_effect=Exception("ollama down")),
        ):
            resp = client.get("/models")

        assert resp.status_code == 200
        assert resp.json()["models"], "should still offer the configured default"

    def test_default_is_always_present_in_the_list(self, client):
        service = AsyncMock()
        service.list_models = AsyncMock(return_value=["something-else"])
        with patch(
            "ai_devops_assistant.services.llm_service.get_llm_service",
            new=AsyncMock(return_value=service),
        ):
            body = client.get("/models").json()

        assert body["default"] in body["models"]
