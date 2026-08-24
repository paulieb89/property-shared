"""EPC/MEES regulatory text must not misstate the law.

Both MCP servers previously claimed, in the `epc-ratings://reference` resource
*and* in the `investment_analysis` prompt, that EPC band C has been required for
new tenancies since April 2025 and that existing tenancies must comply by 2028.

Verified against gov.uk:
  * The current legal minimum for privately rented domestic property in England
    and Wales is band **E** (since 1 April 2020).
  * The proposed future standard is band **C** with a single compliance date of
    **1 October 2030** for all tenancies — the government explicitly rejected an
    earlier date for new tenancies. It is not yet in force.

These assertions cover resources and prompts on *both* servers, because the two
server modules carry independent copies of the same text and a resource-only
test cannot see the prompt copy.
"""

from __future__ import annotations

import json
import re

import pytest

# "2028" and any claim that 2025 is when band C became required are the two
# specific false statements being removed.
_FALSE_2028 = re.compile(r"\b2028\b")
_FALSE_2025_C = re.compile(
    r"(April 2025[^.]*\bband C\b)|(\bband C\b[^.]*April 2025)"
    r"|(from April 2025[^.]*EPC C)|(Since April 2025)",
    re.IGNORECASE,
)


async def _epc_resource_text(mcp) -> str:
    result = await mcp.read_resource("epc-ratings://reference")
    return result.contents[0].content


async def _investment_prompt_text(mcp) -> str:
    result = await mcp.render_prompt(
        "investment_analysis",
        {
            "address": "10 Downing Street",
            "postcode": "SW1A 2AA",
            "purchase_price": "500000",
        },
    )
    return "\n".join(str(m) for m in result.messages)


def _assert_corrected(text: str, where: str) -> None:
    assert not _FALSE_2028.search(text), f"{where}: stale 2028 compliance date still present"
    assert not _FALSE_2025_C.search(text), f"{where}: still claims band C required from April 2025"
    assert "2030" in text, f"{where}: missing the real 1 October 2030 compliance date"


class TestPlainMcpServer:
    @pytest.mark.anyio
    async def test_resource_states_current_minimum_is_e(self):
        from app.mcp.server import mcp

        text = await _epc_resource_text(mcp)
        _assert_corrected(text, "plain MCP epc-ratings resource")

        data = json.loads(text)
        note = data["regulation_note"]
        assert "E" in note, "regulation_note must state band E is the current minimum"
        assert "2030" in note

    @pytest.mark.anyio
    async def test_band_descriptions_are_accurate(self):
        from app.mcp.server import mcp

        data = json.loads(await _epc_resource_text(mcp))
        bands = {b["band"]: b["description"] for b in data["ratings"]}

        # Band C must be described as future/proposed, never as a current rule.
        assert not _FALSE_2025_C.search(bands["C"])
        assert "2030" in bands["C"] or "proposed" in bands["C"].lower()

        # Band E must be described as the current legal minimum.
        assert "minimum" in bands["E"].lower()
        assert not _FALSE_2028.search(bands["E"])

    @pytest.mark.anyio
    async def test_investment_analysis_prompt_is_accurate(self):
        """The prompt carries its own copy — the resource test cannot catch it."""
        from app.mcp.server import mcp

        _assert_corrected(await _investment_prompt_text(mcp), "plain MCP investment_analysis prompt")


class TestMcpAppServer:
    @pytest.mark.anyio
    async def test_resource_states_current_minimum_is_e(self):
        import property_app.tools  # noqa: F401
        from property_app.server import mcp

        text = await _epc_resource_text(mcp)
        _assert_corrected(text, "MCP app epc-ratings resource")

        data = json.loads(text)
        assert "E" in data["regulation_note"]

    @pytest.mark.anyio
    async def test_band_descriptions_are_accurate(self):
        import property_app.tools  # noqa: F401
        from property_app.server import mcp

        data = json.loads(await _epc_resource_text(mcp))
        bands = {b["band"]: b["description"] for b in data["ratings"]}
        assert not _FALSE_2025_C.search(bands["C"])
        assert "2030" in bands["C"] or "proposed" in bands["C"].lower()
        assert "minimum" in bands["E"].lower()

    @pytest.mark.anyio
    async def test_investment_analysis_prompt_is_accurate(self):
        import property_app.tools  # noqa: F401
        from property_app.server import mcp

        _assert_corrected(await _investment_prompt_text(mcp), "MCP app investment_analysis prompt")
