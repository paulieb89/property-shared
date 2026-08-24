"""SSRF remediation tests for property_core/rightmove_scraper.py.

Confirmed vulnerability being closed here: fetch_listing() passed any string
beginning with "http" straight through to session.get() with no host or scheme
validation, and fetch_listings() accepted an arbitrary search URL. Both were
reachable from unauthenticated surfaces (the `rightmove_listing` MCP tool and
the /v1/rightmove/listings + /v1/rightmove/listing/{id} REST endpoints), giving
an unauthenticated caller a server-side fetch primitive against internal hosts.

The assertions below deliberately check that *no outbound request is attempted*
for unsafe input, rather than only checking that an exception is raised — an
exception raised after the request has already gone out would not close the hole.
"""

from __future__ import annotations

import json

import pytest

from property_core import rightmove_scraper
from property_core.rightmove_scraper import (
    RightmoveError,
    extract_property_id,
    fetch_listing,
    fetch_listings,
)
from property_core.url_safety import UnsafeURLError

# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, url, status_code=200, headers=None, body=b"", encoding="utf-8"):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.encoding = encoding
        self.closed = False

    @property
    def text(self) -> str:
        return self._body.decode(self.encoding, errors="replace")

    @property
    def content(self) -> bytes:
        return self._body

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _FakeSession:
    """Records every URL actually requested."""

    def __init__(self, responder):
        self.requested: list[str] = []
        self.requested_kwargs: list[dict] = []
        self.responses: list[_FakeResponse] = []
        self._responder = responder
        self.closed = False

    def get(self, url, **kwargs):
        self.requested.append(url)
        self.requested_kwargs.append(kwargs)
        resp = self._responder(url, **kwargs)
        self.responses.append(resp)
        return resp

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _ExplodingSession(_FakeSession):
    """Fails loudly if any outbound request is attempted at all."""

    def __init__(self):
        super().__init__(responder=None)

    def get(self, url, **kwargs):  # noqa: ARG002
        raise AssertionError(f"SSRF: an outbound request was attempted to {url!r}")


def _install(monkeypatch, session):
    monkeypatch.setattr(rightmove_scraper, "Session", lambda: session)
    return session


def _listing_html(property_id: int = 123456) -> bytes:
    """Minimal but structurally real Rightmove PAGE_MODEL payload."""
    nodes = [{"propertyData": 1}, {"id": 2}, property_id]
    page_model = json.dumps({"data": json.dumps(nodes)})
    return f"window.__PAGE_MODEL = {page_model};".encode()


def _search_html(properties=None) -> bytes:
    payload = {
        "props": {
            "pageProps": {
                "searchResults": {
                    "properties": properties or [],
                    "pagination": {},
                }
            }
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}</script></body></html>"
    ).encode()


# --------------------------------------------------------------------------
# fetch_listing — now ID-only
# --------------------------------------------------------------------------


class TestExtractPropertyId:
    """Library compatibility: downstream servers (property-descriptions-mcp,
    uk-property-mcp) advertise "URL or numeric ID" and pass it straight through.

    A canonical listing URL is therefore still accepted — but only as a source
    of digits. The URL itself is never fetched.
    """

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("123456", "123456"),
            ("  123456  ", "123456"),
            ("https://www.rightmove.co.uk/properties/123456", "123456"),
            ("https://www.rightmove.co.uk/properties/123456/", "123456"),
            ("https://www.rightmove.co.uk/properties/123456?utm=x", "123456"),
            ("https://www.rightmove.co.uk/properties/123456#photos", "123456"),
            ("https://WWW.RIGHTMOVE.CO.UK/properties/123456", "123456"),
            ("https://www.rightmove.co.uk:443/properties/123456", "123456"),
        ],
    )
    def test_legitimate_references_resolve(self, value, expected):
        assert extract_property_id(value) == expected

    @pytest.mark.parametrize(
        "hostile",
        [
            # Wrong host — the SSRF payloads.
            "https://evil.example/properties/123456",
            "http://169.254.169.254/properties/123456",
            "https://127.0.0.1:8080/properties/123456",
            # Host-confusion tricks that a naive "contains rightmove" check misses.
            "https://www.rightmove.co.uk@evil.example/properties/123456",
            "https://www.rightmove.co.uk.evil.example/properties/123456",
            "https://evil.example/www.rightmove.co.uk/properties/123456",
            # Right host, wrong scheme/port.
            "http://www.rightmove.co.uk/properties/123456",
            "https://www.rightmove.co.uk:8080/properties/123456",
            # Right host, but NOT a listing path — must not become a fetch.
            "https://www.rightmove.co.uk/",
            "https://www.rightmove.co.uk/property-for-sale/find.html",
            "https://www.rightmove.co.uk/redirect?to=https://evil.example",
            "https://www.rightmove.co.uk/properties/123456/extra",
            "https://www.rightmove.co.uk/properties/abc",
            "https://www.rightmove.co.uk/properties/",
            "file:///etc/passwd",
            "",
            "not-an-id",
        ],
    )
    def test_hostile_or_malformed_references_rejected(self, hostile):
        with pytest.raises(ValueError):  # UnsafeURLError is a ValueError
            extract_property_id(hostile)


class TestFetchListingInput:
    @pytest.mark.parametrize(
        "hostile",
        [
            "https://evil.example/properties/123456",
            "http://169.254.169.254/latest/meta-data/",
            "https://127.0.0.1:8080/admin",
            "https://www.rightmove.co.uk@evil.example/properties/1",
            "https://www.rightmove.co.uk.evil.example/properties/1",
            "https://www.rightmove.co.uk/redirect?to=https://evil.example",
            "file:///etc/passwd",
        ],
    )
    def test_hostile_urls_refused_without_any_request(self, monkeypatch, hostile):
        """The core SSRF regression: these must never reach the network layer."""
        session = _install(monkeypatch, _ExplodingSession())
        with pytest.raises((ValueError, UnsafeURLError)):
            fetch_listing(hostile)
        assert session.requested == []

    def test_legacy_keyword_argument_still_works(self, monkeypatch):
        """External callers may use fetch_listing(property_url_or_id="...").

        Both known sibling servers call positionally, but this library is
        published on PyPI, so the original parameter name is retained. The name
        has no bearing on validation — the value still goes through
        extract_property_id().
        """
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_listing_html())),
        )
        fetch_listing(property_url_or_id="123456")
        assert session.requested == ["https://www.rightmove.co.uk/properties/123456"]

    def test_legacy_keyword_argument_accepts_a_listing_url(self, monkeypatch):
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_listing_html())),
        )
        fetch_listing(property_url_or_id="https://www.rightmove.co.uk/properties/123456")
        assert session.requested == ["https://www.rightmove.co.uk/properties/123456"]

    def test_legacy_keyword_argument_is_still_validated(self, monkeypatch):
        """Compatibility must not open a validation bypass."""
        session = _install(monkeypatch, _ExplodingSession())
        with pytest.raises((ValueError, UnsafeURLError)):
            fetch_listing(property_url_or_id="https://evil.example/properties/123456")
        assert session.requested == []

    def test_signature_exposes_the_legacy_parameter_name(self):
        """Pin the public name so any future rename is a deliberate decision."""
        import inspect

        assert list(inspect.signature(fetch_listing).parameters)[0] == "property_url_or_id"

    def test_legitimate_url_fetches_the_rebuilt_canonical_url(self, monkeypatch):
        """A valid listing URL works, but the fetched URL is rebuilt from the ID.

        Query string and fragment from the caller's URL are discarded.
        """
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_listing_html())),
        )
        fetch_listing("https://www.rightmove.co.uk/properties/123456?utm_source=evil#x")
        assert session.requested == ["https://www.rightmove.co.uk/properties/123456"]

    @pytest.mark.parametrize(
        "bad_id",
        ["", "  ", "abc", "12a34", "-1", "1.5", "12 34", "1/../../x", "9" * 13],
    )
    def test_non_numeric_or_overlong_ids_refused(self, monkeypatch, bad_id):
        session = _install(monkeypatch, _ExplodingSession())
        with pytest.raises(ValueError):
            fetch_listing(bad_id)
        assert session.requested == []

    def test_numeric_id_builds_canonical_rightmove_url(self, monkeypatch):
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_listing_html())),
        )
        fetch_listing("123456")
        assert session.requested == ["https://www.rightmove.co.uk/properties/123456"]

    def test_session_is_closed_even_when_input_is_rejected(self, monkeypatch):
        session = _install(monkeypatch, _FakeSession(lambda url, **kw: _FakeResponse(url=url)))
        with pytest.raises(ValueError):
            fetch_listing("not-an-id")
        assert session.closed or session.requested == []


# --------------------------------------------------------------------------
# fetch_listings — allowlisted search URLs only
# --------------------------------------------------------------------------


class TestFetchListingsHostAllowlist:
    @pytest.mark.parametrize(
        "hostile",
        [
            "https://evil.example/search",
            "https://www.rightmove.co.uk.evil.example/search",
            "https://www.rightmove.co.uk@evil.example/search",
            "http://www.rightmove.co.uk/search",
            "https://www.rightmove.co.uk:8080/search",
            "https://169.254.169.254/",
        ],
    )
    def test_unsafe_search_urls_refused_without_any_request(self, monkeypatch, hostile):
        session = _install(monkeypatch, _ExplodingSession())
        with pytest.raises((ValueError, UnsafeURLError, RightmoveError)):
            fetch_listings(hostile)
        assert session.requested == []

    def test_allowlisted_search_url_is_fetched(self, monkeypatch):
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_search_html())),
        )
        url = "https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=X"
        assert fetch_listings(url, max_pages=1) == []
        assert session.requested and session.requested[0].startswith(
            "https://www.rightmove.co.uk/"
        )

    def test_redirects_are_not_delegated_to_the_http_client(self, monkeypatch):
        """The whole redirect defense rests on allow_redirects=False.

        Without this assertion, deleting `allow_redirects=False` from
        _make_request leaves every redirect test green — requests would follow
        redirects itself, _make_request would never observe a 3xx, and an
        allowlisted host could bounce us anywhere. Assert the kwarg directly.
        """
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_search_html())),
        )
        fetch_listings(
            "https://www.rightmove.co.uk/property-for-sale/find.html?a=b", max_pages=1
        )
        assert session.requested_kwargs, "no request was made"
        for kwargs in session.requested_kwargs:
            assert kwargs.get("allow_redirects") is False, (
                "allow_redirects must be False so each hop is re-validated"
            )
            assert kwargs.get("stream") is True, (
                "stream must be True so the byte cap applies before the body is buffered"
            )

    def test_listing_detail_also_disables_client_redirects(self, monkeypatch):
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_listing_html())),
        )
        fetch_listing("123456")
        assert session.requested_kwargs
        for kwargs in session.requested_kwargs:
            assert kwargs.get("allow_redirects") is False
            assert kwargs.get("stream") is True

    def test_fetched_url_is_the_canonicalised_value_not_the_raw_input(self, monkeypatch):
        """Guards against 'validate A, fetch B' parser-differential drift."""
        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_search_html())),
        )
        fetch_listings(
            "https://www.rightmove.co.uk:443/property-for-sale/find.html?a=b", max_pages=1
        )
        assert session.requested[0] == "https://www.rightmove.co.uk/property-for-sale/find.html?a=b"


# --------------------------------------------------------------------------
# Redirect handling
# --------------------------------------------------------------------------


class TestRedirects:
    def _redirecting(self, location, *, status=302):
        def responder(url, **kwargs):  # noqa: ARG001
            if "find.html" in url and "redirected" not in url:
                headers = {} if location is None else {"Location": location}
                return _FakeResponse(url=url, status_code=status, headers=headers)
            return _FakeResponse(url=url, body=_search_html())

        return responder

    START = "https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=X"

    def test_cross_host_redirect_is_not_followed(self, monkeypatch):
        session = _install(monkeypatch, _FakeSession(self._redirecting("https://evil.example/x")))
        with pytest.raises((RightmoveError, UnsafeURLError, ValueError)):
            fetch_listings(self.START, max_pages=1)
        assert not any("evil.example" in u for u in session.requested)

    def test_protocol_relative_redirect_is_not_followed(self, monkeypatch):
        session = _install(monkeypatch, _FakeSession(self._redirecting("//evil.example/x")))
        with pytest.raises((RightmoveError, UnsafeURLError, ValueError)):
            fetch_listings(self.START, max_pages=1)
        assert not any("evil.example" in u for u in session.requested)

    def test_redirect_without_location_is_rejected(self, monkeypatch):
        _install(monkeypatch, _FakeSession(self._redirecting(None)))
        with pytest.raises(RightmoveError):
            fetch_listings(self.START, max_pages=1)

    def test_same_host_relative_redirect_is_followed(self, monkeypatch):
        session = _install(
            monkeypatch, _FakeSession(self._redirecting("/property-for-sale/redirected.html"))
        )
        fetch_listings(self.START, max_pages=1)
        assert session.requested[-1] == (
            "https://www.rightmove.co.uk/property-for-sale/redirected.html"
        )

    def test_redirect_loop_is_bounded(self, monkeypatch):
        def responder(url, **kwargs):  # noqa: ARG001
            return _FakeResponse(
                url=url,
                status_code=302,
                headers={"Location": "https://www.rightmove.co.uk/loop"},
            )

        session = _install(monkeypatch, _FakeSession(responder))
        with pytest.raises(RightmoveError):
            fetch_listings(self.START, max_pages=1)
        assert len(session.requested) <= 6, "redirect chain must be capped"


# --------------------------------------------------------------------------
# Response size caps
# --------------------------------------------------------------------------


class TestResponseSizeCap:
    START = "https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=X"

    def test_oversized_content_length_rejected(self, monkeypatch):
        def responder(url, **kwargs):  # noqa: ARG001
            return _FakeResponse(
                url=url,
                headers={"Content-Length": str(50 * 1024 * 1024)},
                body=b"x" * 10,
            )

        _install(monkeypatch, _FakeSession(responder))
        with pytest.raises(RightmoveError):
            fetch_listings(self.START, max_pages=1)

    def test_oversized_stream_rejected_and_response_closed(self, monkeypatch):
        """No Content-Length (or a spoofed one) must still be capped while streaming."""

        def responder(url, **kwargs):  # noqa: ARG001
            return _FakeResponse(url=url, headers={}, body=b"x" * (30 * 1024 * 1024))

        session = _install(monkeypatch, _FakeSession(responder))
        with pytest.raises(RightmoveError):
            fetch_listings(self.START, max_pages=1)
        assert session.responses and all(r.closed for r in session.responses)


class TestPublicMcpSurfaceStaysNumericOnly:
    """The library accepts a canonical listing URL for downstream compatibility;
    the public MCP tool deliberately does not widen its input."""

    @pytest.mark.anyio
    async def test_mcp_tool_rejects_listing_url(self, monkeypatch):
        from app.mcp.server import rightmove_listing

        session = _install(monkeypatch, _ExplodingSession())
        with pytest.raises(ValueError):
            await rightmove_listing("https://www.rightmove.co.uk/properties/123456")
        assert session.requested == []

    @pytest.mark.anyio
    async def test_mcp_tool_accepts_numeric_id(self, monkeypatch):
        from app.mcp.server import rightmove_listing

        session = _install(
            monkeypatch,
            _FakeSession(lambda url, **kw: _FakeResponse(url=url, body=_listing_html())),
        )
        await rightmove_listing("123456")
        assert session.requested == ["https://www.rightmove.co.uk/properties/123456"]
