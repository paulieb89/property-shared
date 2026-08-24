"""URL allowlist validation for outbound server-side fetches.

Any code path that fetches a URL influenced by caller input must run it through
:func:`validate_allowed_url` first, and must then fetch the *returned* value.

Fetching the returned value rather than the original string is what closes the
parser-differential gap: this module validates with :mod:`urllib.parse`, while
the HTTP client does its own independent parsing. Reconstructing the URL from
components that have already been validated removes any opportunity for the two
parsers to disagree about which host is really being contacted.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

# Backslashes and raw whitespace/control characters are the classic way two URL
# parsers end up disagreeing about where the authority ends (some treat "\" as
# "/", some strip control characters, some do neither). Rejecting them outright
# is cheaper and safer than trying to model every parser's normalisation rules.
_DISALLOWED_CHARS = frozenset(
    "\\ \t\n\r\x0b\x0c\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    "\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f\x7f"
)


class UnsafeURLError(ValueError):
    """Raised when a URL fails scheme/host/port validation or cannot be parsed.

    Subclasses ``ValueError`` to match the repo convention that invalid input
    raises ``ValueError`` (see .claude/rules/property-core.md).
    """


def validate_allowed_url(url: str, *, allowed_hosts: frozenset[str]) -> str:
    """Validate ``url`` against ``allowed_hosts`` and return a canonical form.

    Enforces: https only, no userinfo, default port only, and an exact
    (case-insensitive) hostname match against ``allowed_hosts``. Suffix and
    substring matches are deliberately not accepted, so neither
    ``https://www.rightmove.co.uk.evil.example/`` nor
    ``https://evil.example/www.rightmove.co.uk`` can pass.

    Args:
        url: The candidate URL.
        allowed_hosts: Exact hostnames permitted for this call site.

    Returns:
        A canonical URL rebuilt from the validated components. **Callers must
        fetch this value, not the original input.**

    Raises:
        UnsafeURLError: If the URL is malformed or fails any check.
    """
    if not isinstance(url, str) or not url:
        raise UnsafeURLError("URL must be a non-empty string")

    bad = _DISALLOWED_CHARS & set(url)
    if bad:
        raise UnsafeURLError(
            f"URL contains disallowed characters: {sorted(repr(c) for c in bad)}"
        )

    try:
        # urlsplit, not urlparse: urlparse peels off a ";params" segment, which
        # urlunparse would then silently drop from the canonical URL.
        parsed = urlsplit(url)
    except ValueError as exc:  # pragma: no cover - defensive
        raise UnsafeURLError(f"URL could not be parsed: {exc}") from exc

    if parsed.scheme != "https":
        raise UnsafeURLError(f"URL scheme must be https, got {parsed.scheme!r}")

    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("URL must not contain userinfo (user:pass@host)")

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError(f"URL port could not be parsed: {exc}") from exc
    if port not in (None, 443):
        raise UnsafeURLError(f"URL port must be the https default, got {port!r}")

    hostname = parsed.hostname
    if not hostname or hostname.lower() not in allowed_hosts:
        raise UnsafeURLError(f"Host {hostname!r} is not allowlisted")

    # Rebuild from validated parts only. The fragment is dropped (it is never
    # transmitted to the server) and the port is left implicit.
    return urlunsplit(("https", hostname.lower(), parsed.path or "/", parsed.query, ""))
