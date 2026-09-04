"""Rightmove location lookup separates caller error, absence and upstream failure.

`build_search_url` raised a single bare `LocationLookupError` both when the
upstream connection failed and when the upstream answered normally with no
match. Those are different facts about the world and they need different
remedies, so a consumer that can only see one type cannot choose between
"reformulate your input", "that place has no Rightmove record" and "try again".

The grammar is settled by a live probe (2026-09-03), not by the docstring:

    'SW1A 1AA' -> 'POSTCODE^837246'   full postcode: resolves
    'B5 4BX'   -> 'POSTCODE^4991456'  full postcode: resolves
    'B5'       -> 'OUTCODE^86'        outcode:       resolves
    'NG1'      -> 'OUTCODE^1752'      outcode:       resolves
    'B5 7'     -> None                sector:        never resolves
    'E14 9'    -> None                sector:        never resolves
    'XX99 9XX' -> None                well-formed, nonexistent

So outcodes must keep working -- narrowing this to full postcodes only would be
a breaking change for a documented input -- while a sector must be refused
before it reaches Rightmove, because no sector can ever resolve.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from property_core.exceptions import InvalidPostcodeError, PPDError
from property_core.rightmove_location import (
    LocationLookupError,
    LocationNotFoundError,
    RightmoveLocationAPI,
)

import requests


def _matches(location_id: str, location_type: str) -> dict:
    return {"matches": [{"id": location_id, "type": location_type}]}


NO_MATCH = {"matches": []}


@pytest.fixture
def api():
    # Cache off: a cached identifier would let a later assertion pass without
    # the request under test ever being made.
    return RightmoveLocationAPI(cache_enabled=False, rate_limit_delay=0)


# --- (i) shapes Rightmove can never resolve: caller error, before any request ---


@pytest.mark.parametrize("sector", ["B5 7", "E14 9", "SW1A 1", "GIR 0"])
def test_a_sector_is_rejected_before_any_request(api, sector):
    with patch.object(requests, "get") as get:
        with pytest.raises(InvalidPostcodeError):
            api.lookup_postcode(sector)
        assert get.call_count == 0, "a sector can never resolve; it must not reach Rightmove"


def test_the_sector_message_names_the_outcode_that_would_work(api):
    with patch.object(requests, "get"):
        with pytest.raises(InvalidPostcodeError) as exc:
            api.lookup_postcode("B5 7")
    # A caller told only "not valid" goes hunting for a typo that is not there.
    assert "'B5'" in str(exc.value)


@pytest.mark.parametrize(
    "garbage",
    ["", "   ", "NOTAPOSTCODE", "B5;DROP", "../etc", "B5\n7", "12345", "B5 4BX EXTRA", "<script>"],
)
def test_garbage_is_rejected_before_any_request(api, garbage):
    with patch.object(requests, "get") as get:
        with pytest.raises(InvalidPostcodeError):
            api.lookup_postcode(garbage)
        get.assert_not_called()


def test_a_non_string_is_rejected_rather_than_coerced(api):
    with patch.object(requests, "get") as get:
        with pytest.raises(InvalidPostcodeError):
            api.lookup_postcode(None)  # type: ignore[arg-type]
        get.assert_not_called()


# --- inputs that DO resolve must keep resolving ---


@pytest.mark.parametrize("outcode", ["B5", "NG1", "SW1A", "EC1V", "B50", "GIR"])
def test_outcodes_reach_the_upstream_and_resolve(api, outcode):
    with patch.object(requests, "get") as get:
        get.return_value.json.return_value = _matches("86", "OUTCODE")
        get.return_value.raise_for_status.return_value = None
        assert api.lookup_postcode(outcode) == "OUTCODE^86"
        assert get.call_count == 1, "an outcode is a documented input and must reach Rightmove"


@pytest.mark.parametrize("postcode", ["SW1A 1AA", "B5 4BX", "GIR 0AA"])
def test_full_postcodes_reach_the_upstream_and_resolve(api, postcode):
    with patch.object(requests, "get") as get:
        get.return_value.json.return_value = _matches("837246", "POSTCODE")
        get.return_value.raise_for_status.return_value = None
        assert api.lookup_postcode(postcode) == "POSTCODE^837246"


def test_whitespace_and_case_are_normalised_not_rejected(api):
    with patch.object(requests, "get") as get:
        get.return_value.json.return_value = _matches("4991456", "POSTCODE")
        get.return_value.raise_for_status.return_value = None
        api.lookup_postcode(" b5   4bx ")
        assert get.call_args.kwargs["params"]["query"] == "B5 4BX"


# --- (ii) well-formed but no match: absence, not caller error ---


def test_a_wellformed_unknown_postcode_is_not_found_not_invalid(api):
    with patch.object(requests, "get") as get:
        get.return_value.json.return_value = NO_MATCH
        get.return_value.raise_for_status.return_value = None
        with pytest.raises(LocationNotFoundError) as exc:
            api.build_search_url("XX99 9XX")
    # The input satisfies the grammar; calling it invalid states a false fact.
    assert not isinstance(exc.value, InvalidPostcodeError)


def test_lookup_postcode_still_returns_none_for_no_match(api):
    """`lookup_postcode` can express absence, so it keeps its Optional contract.

    Only `build_search_url` must convert, because it has to return a URL.
    """
    with patch.object(requests, "get") as get:
        get.return_value.json.return_value = NO_MATCH
        get.return_value.raise_for_status.return_value = None
        assert api.lookup_postcode("XX99 9XX") is None


def test_a_match_without_an_id_is_absence_not_a_crash(api):
    with patch.object(requests, "get") as get:
        get.return_value.json.return_value = {"matches": [{"type": "OUTCODE"}]}
        get.return_value.raise_for_status.return_value = None
        assert api.lookup_postcode("B5") is None


# --- (iii) transport failure stays an upstream failure ---


def test_transport_failure_stays_a_lookup_error_and_is_retryable(api):
    with patch.object(requests, "get", side_effect=requests.RequestException("boom")):
        with pytest.raises(LocationLookupError) as exc:
            api.lookup_postcode("B5 4BX")
    assert exc.value.retryable is True
    assert exc.value.to_dict()["error"] == "rightmove_location_unavailable"


# --- the three outcomes must stay tellable apart, and reach the consumers ---


def test_the_three_outcomes_are_pairwise_distinguishable():
    """No two of these may be catchable by the same `except` unless intended.

    They differ only by subclass, so a consumer mapping them to 422 / 404 / 502
    depends on exactly this.
    """
    assert not issubclass(LocationNotFoundError, InvalidPostcodeError)
    assert not issubclass(InvalidPostcodeError, LocationNotFoundError)
    assert not issubclass(LocationLookupError, LocationNotFoundError)
    assert not issubclass(LocationNotFoundError, LocationLookupError)
    assert not issubclass(LocationLookupError, InvalidPostcodeError)


def test_all_three_are_ppd_errors_so_the_cli_decorator_catches_them():
    """`_ppd_errors` catches the base, so subclassing is what wires the CLI up."""
    for exc_type in (InvalidPostcodeError, LocationNotFoundError, LocationLookupError):
        assert issubclass(exc_type, PPDError)


def test_all_three_carry_a_typed_payload():
    for exc in (
        InvalidPostcodeError("B5 7", field="postcode", expected="an outcode"),
        LocationNotFoundError("XX99 9XX"),
        LocationLookupError("boom"),
    ):
        payload = exc.to_dict()
        assert payload["error"] and payload["detail"]
        assert "retryable" in payload


def test_the_typed_errors_are_exported_from_property_core():
    import property_core

    for name in ("LocationNotFoundError", "LocationLookupError"):
        assert hasattr(property_core, name), f"{name} must be importable from property_core"
        assert name in property_core.__all__


# --- build_search_url is the layer that converts, and it still builds URLs ---


def test_build_search_url_still_builds_a_url_for_a_resolvable_input(api):
    with patch.object(requests, "get") as get:
        get.return_value.json.return_value = _matches("86", "OUTCODE")
        get.return_value.raise_for_status.return_value = None
        url = api.build_search_url("B5")
    assert "locationIdentifier=OUTCODE%5E86" in url


def test_a_sector_is_refused_by_build_search_url_too(api):
    with patch.object(requests, "get") as get:
        with pytest.raises(InvalidPostcodeError):
            api.build_search_url("B5 7")
        get.assert_not_called()
