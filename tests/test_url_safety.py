"""Unit tests for the URL allowlist helper used to close the Rightmove SSRF paths.

The scraper previously accepted any string beginning with "http" and fetched it
server-side (property_core/rightmove_scraper.py::_normalize_property_url), which
was reachable from an unauthenticated MCP tool and two unauthenticated REST
endpoints. These tests pin the validation contract that replaces that behaviour.
"""

from __future__ import annotations

import pytest

from property_core.url_safety import UnsafeURLError, validate_allowed_url

RIGHTMOVE = frozenset({"www.rightmove.co.uk"})
MEDIA = frozenset({"media.rightmove.co.uk"})


class TestAccepts:
    def test_allowlisted_https_host(self):
        url = "https://www.rightmove.co.uk/properties/123456"
        assert validate_allowed_url(url, allowed_hosts=RIGHTMOVE) == url

    def test_preserves_query_string(self):
        url = "https://www.rightmove.co.uk/property-for-sale/find.html?index=24&radius=0.25"
        out = validate_allowed_url(url, allowed_hosts=RIGHTMOVE)
        assert "index=24" in out and "radius=0.25" in out

    def test_explicit_default_port_is_allowed(self):
        out = validate_allowed_url(
            "https://www.rightmove.co.uk:443/properties/1", allowed_hosts=RIGHTMOVE
        )
        # Canonicalised back to the implicit default port.
        assert out == "https://www.rightmove.co.uk/properties/1"

    def test_separate_allowlists_are_independent(self):
        media = "https://media.rightmove.co.uk/photo.jpeg"
        assert validate_allowed_url(media, allowed_hosts=MEDIA) == media
        # ...but the media host is not valid for the search/listing allowlist.
        with pytest.raises(UnsafeURLError):
            validate_allowed_url(media, allowed_hosts=RIGHTMOVE)


class TestRejects:
    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example/x",
            # Lookalike hosts — the exact bypass the old startswith() check allowed.
            "https://www.rightmove.co.uk.evil.example/x",
            "https://wwwXrightmoveXco.uk/x",
            "https://evil.example/www.rightmove.co.uk",
            # Userinfo tricks: the real host here is evil.example.
            "https://www.rightmove.co.uk@evil.example/x",
            "https://user:pass@evil.example/x",
            # Credentials even on an allowlisted host.
            "https://user:pass@www.rightmove.co.uk/x",
            # Non-https schemes.
            "http://www.rightmove.co.uk/properties/1",
            "file:///etc/passwd",
            "gopher://www.rightmove.co.uk/x",
            # Non-default ports.
            "https://www.rightmove.co.uk:8080/x",
            "https://www.rightmove.co.uk:22/x",
            # Internal / cloud-metadata targets — the classic SSRF payloads.
            "https://127.0.0.1/x",
            "https://localhost/x",
            "https://169.254.169.254/latest/meta-data/",
            "https://[::1]/x",
        ],
    )
    def test_unsafe_urls_raise(self, url):
        with pytest.raises(UnsafeURLError):
            validate_allowed_url(url, allowed_hosts=RIGHTMOVE)

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.rightmove.co.uk\\@evil.example/x",
            "https:\\\\evil.example/x",
            "https://www.rightmove.co.uk/x\nHost: evil.example",
            "https://www.rightmove.co.uk/x\r\nX: y",
            "https://www.rightmove.co.uk\t/x",
            "https://www.rightmove.co.uk/x\x00",
        ],
    )
    def test_control_chars_and_backslashes_raise(self, url):
        """Parser-differential guards.

        Backslashes and control characters are the classic way two URL parsers
        disagree about where the host ends. Rejecting them outright means we
        never validate one interpretation while the HTTP client fetches another.
        """
        with pytest.raises(UnsafeURLError):
            validate_allowed_url(url, allowed_hosts=RIGHTMOVE)

    def test_malformed_url_raises_unsafe_not_raw_valueerror(self):
        """A parse failure must surface as UnsafeURLError, never a raw ValueError.

        Callers map UnsafeURLError to a clean 4xx/RightmoveError; a leaked
        ValueError would become an unhandled 500.
        """
        with pytest.raises(UnsafeURLError):
            validate_allowed_url("https://www.rightmove.co.uk:notaport/x", allowed_hosts=RIGHTMOVE)

    def test_empty_and_relative_urls_raise(self):
        for url in ("", "/properties/123", "www.rightmove.co.uk/x"):
            with pytest.raises(UnsafeURLError):
                validate_allowed_url(url, allowed_hosts=RIGHTMOVE)


class TestCanonicalisation:
    """The returned value — not the input — is what callers must fetch."""

    def test_returns_canonical_form_built_from_validated_parts(self):
        out = validate_allowed_url(
            "https://www.rightmove.co.uk:443/properties/1?a=b#fragment",
            allowed_hosts=RIGHTMOVE,
        )
        assert out.startswith("https://www.rightmove.co.uk/")
        assert "#" not in out, "fragment must be dropped"
        assert "a=b" in out

    def test_empty_path_is_canonicalised_to_root(self):
        out = validate_allowed_url("https://www.rightmove.co.uk", allowed_hosts=RIGHTMOVE)
        assert out == "https://www.rightmove.co.uk/"

    def test_output_revalidates_cleanly(self):
        """Canonical output must itself pass validation (idempotence)."""
        once = validate_allowed_url(
            "https://www.rightmove.co.uk:443/properties/1?a=b", allowed_hosts=RIGHTMOVE
        )
        assert validate_allowed_url(once, allowed_hosts=RIGHTMOVE) == once
