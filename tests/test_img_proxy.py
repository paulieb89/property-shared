"""SSRF tests for the /img proxy in property_app/server.py.

The proxy previously accepted any URL passing a bare
``url.startswith("https://media.rightmove.co.uk")`` prefix check, which lookalike
hosts and userinfo tricks both defeat, and it followed redirects automatically
with no size cap.

Validation here goes through httpx's own URL parser (never urllib.parse), because
httpx is what actually issues the request — validating with a different parser
would reinstate the very host-confusion bug being fixed.
"""

from __future__ import annotations

import httpx
import pytest

from property_app.server import _IMG_MAX_BYTES, _validated_img_url, proxy_image


class TestRejects:
    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://evil.example/x.jpg",
            # Defeats a bare startswith() prefix check:
            "https://media.rightmove.co.uk.evil.example/x.jpg",
            # Real host here is evil.example — the userinfo trick:
            "https://media.rightmove.co.uk@evil.example/x.jpg",
            "https://user:pass@evil.example/x.jpg",
            "https://user:pass@media.rightmove.co.uk/x.jpg",
            "http://media.rightmove.co.uk/x.jpg",
            "https://media.rightmove.co.uk:8080/x.jpg",
            "https://127.0.0.1/x.jpg",
            "https://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "not a url",
            # Parser-differential characters.
            "https://media.rightmove.co.uk\\@evil.example/x.jpg",
            "https://media.rightmove.co.uk/x.jpg\nHost: evil.example",
            "https://media.rightmove.co.uk\t/x.jpg",
        ],
    )
    def test_unsafe_urls_rejected(self, url):
        assert _validated_img_url(url) is None


class TestAccepts:
    def test_allowlisted_image_url(self):
        url = _validated_img_url("https://media.rightmove.co.uk/dir/IMG_01.jpeg")
        assert url is not None
        assert url.host == "media.rightmove.co.uk"
        assert url.scheme == "https"

    def test_query_string_preserved(self):
        url = _validated_img_url("https://media.rightmove.co.uk/x.jpeg?w=100")
        assert url is not None
        assert b"w=100" in url.query


class _Req:
    """Minimal stand-in for a Starlette request."""

    def __init__(self, url):
        self.query_params = {"url": url}


def _mock_transport(monkeypatch, handler):
    """Route proxy_image's httpx calls to `handler`, recording each request."""
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real_client(*args, **kwargs)

    # proxy_image does `import httpx` at call time, so patching the module
    # attribute here is what it will resolve.
    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    return seen


class TestProxyImageBehaviour:
    """Covers proxy_image itself, not just the URL validator."""

    @pytest.mark.anyio
    async def test_rejects_unsafe_url_without_any_request(self, monkeypatch):
        seen = _mock_transport(
            monkeypatch, lambda req: httpx.Response(200, content=b"x", headers={})
        )
        resp = await proxy_image(_Req("https://media.rightmove.co.uk@evil.example/x.jpg"))
        assert resp.status_code == 400
        assert seen == []

    @pytest.mark.anyio
    async def test_does_not_delegate_redirects_to_httpx(self, monkeypatch):
        """If follow_redirects were True, httpx would chase the 302 itself."""
        seen = _mock_transport(
            monkeypatch,
            lambda req: httpx.Response(
                302, headers={"Location": "https://evil.example/x.jpg"}
            ),
        )
        resp = await proxy_image(_Req("https://media.rightmove.co.uk/a.jpg"))
        assert resp.status_code == 400, "cross-host redirect must be refused"
        assert [str(r.url) for r in seen] == ["https://media.rightmove.co.uk/a.jpg"]
        assert not any("evil.example" in str(r.url) for r in seen)

    @pytest.mark.anyio
    async def test_same_host_redirect_is_followed(self, monkeypatch):
        def handler(req):
            if req.url.path == "/a.jpg":
                return httpx.Response(302, headers={"Location": "/b.jpg"})
            return httpx.Response(
                200, content=b"IMG", headers={"content-type": "image/jpeg"}
            )

        seen = _mock_transport(monkeypatch, handler)
        resp = await proxy_image(_Req("https://media.rightmove.co.uk/a.jpg"))
        assert resp.status_code == 200
        assert [r.url.path for r in seen] == ["/a.jpg", "/b.jpg"]

    @pytest.mark.anyio
    async def test_non_image_content_type_is_refused(self, monkeypatch):
        """media.rightmove.co.uk carries third-party files; never echo text/html."""
        _mock_transport(
            monkeypatch,
            lambda req: httpx.Response(
                200, content=b"<script>alert(1)</script>", headers={"content-type": "text/html"}
            ),
        )
        resp = await proxy_image(_Req("https://media.rightmove.co.uk/evil.html"))
        assert resp.status_code == 502

    @pytest.mark.anyio
    async def test_successful_image_sets_nosniff(self, monkeypatch):
        _mock_transport(
            monkeypatch,
            lambda req: httpx.Response(
                200, content=b"IMG", headers={"content-type": "image/jpeg"}
            ),
        )
        resp = await proxy_image(_Req("https://media.rightmove.co.uk/a.jpg"))
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.anyio
    async def test_oversized_body_is_capped(self, monkeypatch):
        _mock_transport(
            monkeypatch,
            lambda req: httpx.Response(
                200,
                content=b"x" * (_IMG_MAX_BYTES + 1024),
                headers={"content-type": "image/jpeg"},
            ),
        )
        resp = await proxy_image(_Req("https://media.rightmove.co.uk/big.jpg"))
        assert resp.status_code == 502

    @pytest.mark.anyio
    async def test_plus_in_image_url_is_not_rejected(self, monkeypatch):
        """Starlette decodes '+' to ' '; rejecting spaces silently broke images."""
        _mock_transport(
            monkeypatch,
            lambda req: httpx.Response(
                200, content=b"IMG", headers={"content-type": "image/jpeg"}
            ),
        )
        resp = await proxy_image(_Req("https://media.rightmove.co.uk/dir/IMG 01+02.jpeg"))
        assert resp.status_code == 200


class TestRedirectResolution:
    """A redirect target must be re-validated with the same parser."""

    def test_cross_host_redirect_target_rejected(self):
        base = _validated_img_url("https://media.rightmove.co.uk/a/b.jpeg")
        assert base is not None
        assert _validated_img_url(str(base.join("https://evil.example/x"))) is None

    def test_protocol_relative_redirect_target_rejected(self):
        base = _validated_img_url("https://media.rightmove.co.uk/a/b.jpeg")
        assert base is not None
        assert _validated_img_url(str(base.join("//evil.example/x"))) is None

    def test_same_host_relative_redirect_target_allowed(self):
        base = _validated_img_url("https://media.rightmove.co.uk/a/b.jpeg")
        assert base is not None
        nxt = _validated_img_url(str(base.join("/c/d.jpeg")))
        assert nxt is not None
        assert nxt.host == "media.rightmove.co.uk"
        assert nxt.path == "/c/d.jpeg"
