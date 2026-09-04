"""The typed Rightmove errors reach the MCP and CLI surfaces readably.

Neither MCP server needs a code change: FastMCP renders `str(exc)` for an
exception raised inside a tool, so a self-describing typed error arrives as a
readable message on its own. These tests pin that, because "no change needed"
is a claim about behaviour and should fail loudly if it stops being true.

The target shape is the one a real ChatGPT session produced for the equivalent
PPD error (docs/ops/2026-08-30-property-shared-stall.md):

    Error calling tool 'ppd_transactions': postcode 'DE12' is not valid;
    expected a full UK postcode, e.g. 'B5 4BX'
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _call_rightmove_search(mcp, postcode: str) -> str:
    """Drive the real FastMCP dispatcher and return the error text it renders."""
    from fastmcp import Client

    async with Client(mcp) as client:
        with pytest.raises(Exception) as exc:  # noqa: PT011 - FastMCP's own wrapper type
            await client.call_tool("rightmove_search", {"postcode": postcode})
    return str(exc.value)


async def test_the_plain_mcp_server_reports_a_sector_readably():
    from app.mcp.server import mcp

    message = await _call_rightmove_search(mcp, "B5 7")
    assert "not valid" in message
    assert "'B5'" in message, "the remedy must survive to the model"
    assert "Traceback" not in message, "a stack trace is not an answer"


async def test_the_mcp_app_server_reports_a_sector_readably():
    # property_app registers its tools inside main(), not at server import, so
    # the tools module must be imported for the dispatcher to know them.
    from property_app import tools  # noqa: F401
    from property_app.server import mcp

    message = await _call_rightmove_search(mcp, "B5 7")
    assert "not valid" in message
    assert "Traceback" not in message


def test_a_refused_input_never_reaches_rightmove_from_mcp():
    """The shape gate sits at the network boundary, so no request is spent."""
    from property_core.rightmove_location import RightmoveLocationAPI
    from property_core.exceptions import InvalidPostcodeError

    api = RightmoveLocationAPI(cache_enabled=False, rate_limit_delay=0)
    with patch("property_core.rightmove_location.requests.get") as get:
        with pytest.raises(InvalidPostcodeError):
            api.build_search_url("B5 7")
        assert get.call_count == 0


# --- CLI: core mode only, deliberately ---


def _invoke(args: list[str]):
    from typer.testing import CliRunner

    import property_cli.main as M

    return CliRunner().invoke(M.app, args)


@pytest.mark.parametrize(
    "args",
    [
        ["rightmove", "search-url", "B5 7"],
        ["rightmove", "listings", "B5 7"],
    ],
)
def test_cli_core_mode_exits_1_with_typed_json_not_a_traceback(args):
    """`@_ppd_errors` catches the base class, so subclassing is what wires this up.

    Scope note: this covers CORE mode only. In `--api-url` mode the request goes
    through `HTTPClient.get`, which calls `raise_for_status()` and discards the
    typed body, so a 422/404 surfaces as `httpx.HTTPStatusError` and escapes this
    decorator. Fixing that means teaching `HTTPClient` to rebuild the typed error
    from the response body, which applies to every `--api-url` command, not just
    these two -- tracked separately rather than smuggled in here.
    """
    result = _invoke(args)
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output
    # _echo_json pretty-prints across several lines, so parse the whole payload.
    payload = json.loads(result.output)
    assert payload["error"] == "invalid_postcode"
    assert payload["retryable"] is False
    assert "'B5'" in payload["expected"]


def test_cli_core_mode_still_accepts_an_outcode():
    with patch("property_core.rightmove_location.requests.get") as get:
        get.return_value.json.return_value = {"matches": [{"id": "86", "type": "OUTCODE"}]}
        get.return_value.raise_for_status.return_value = None
        result = _invoke(["rightmove", "search-url", "B5"])
    assert result.exit_code == 0, result.output
    assert "OUTCODE%5E86" in result.output
