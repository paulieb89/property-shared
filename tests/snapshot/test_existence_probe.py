"""The bounded existence probe: what an empty result is allowed to mean.

Spec section 2.4 and tests 10-14, decision O1.

`ppd_transactions` and CLI `ppd search` take no date. Against a snapshot the
call means "latest within coverage", so a postcode last sold in 2009 returns an
empty list -- which an LLM reads as "never sold". That is a confident false
claim, and the probe exists to make it impossible.

The asymmetry is the point: `true` and `null` both add a warning, `false` is the
only value that licenses a bare empty result, and `false` may only be set by a
probe that actually completed.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.ppd_service import PPDService  # noqa: E402


def test_probe_is_not_issued_when_the_snapshot_returns_rows(snapshot_routing, probe_spy):
    """Spec test 13. A non-empty result answers the question already."""
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5", limit=10)
    assert result["count"] > 0
    assert probe_spy.calls == []
    assert result["provenance"].older_records_exist is None
    assert not any("earlier records" in w for w in result["provenance"].warnings)


def test_empty_with_nothing_older_is_an_honest_empty(snapshot_routing, probe_spy):
    """Spec test 10. No warning: the absence is real and complete."""
    probe_spy.result = False
    svc = PPDService()
    result = svc.search_transactions(postcode="ZZ9 9ZZ", postcode_prefix=None, limit=10)
    assert result["count"] == 0
    assert len(probe_spy.calls) == 1
    provenance = result["provenance"]
    assert provenance.older_records_exist is False
    assert not any("earlier" in w or "cannot determine" in w
                   for w in provenance.warnings)


def test_empty_with_older_records_warns(snapshot_routing, probe_spy):
    """Spec test 11."""
    probe_spy.result = True
    svc = PPDService()
    result = svc.search_transactions(postcode="ZZ9 9ZZ", postcode_prefix=None, limit=10)
    provenance = result["provenance"]
    assert provenance.older_records_exist is True
    assert any("earlier records exist outside coverage" in w
               for w in provenance.warnings)
    assert any("2016-01-01" in w for w in provenance.warnings)


def test_probe_failure_is_null_and_never_false(snapshot_routing, probe_spy):
    """Spec test 12. `false` asserts a fact about the world; a timeout asserts nothing."""
    probe_spy.raises = TimeoutError("probe timed out")
    svc = PPDService()
    result = svc.search_transactions(postcode="ZZ9 9ZZ", postcode_prefix=None, limit=10)
    provenance = result["provenance"]
    assert provenance.older_records_exist is None
    assert provenance.older_records_exist is not False
    assert any("coverage probe unavailable" in w for w in provenance.warnings)

    payload = str(result) + str(provenance.model_dump(mode="json"))
    assert "never sold" not in payload.lower()


def test_probe_uses_limit_one_existence_and_is_not_retried(snapshot_routing,
                                                           recording_sparql):
    """Spec test 14. Never COUNT, never retried, bounded at three seconds."""
    from property_core.ppd_probe import ExistenceProbe

    probe = ExistenceProbe(client=recording_sparql.client)
    assert probe.older_records_exist(postcode="ZZ9 9ZZ", postcode_prefix=None,
                                     coverage_from="2016-01-01") is False

    assert len(recording_sparql.queries) == 1
    query = recording_sparql.queries[0]
    assert "LIMIT 1" in query
    # The aggregate, not the substring: `?county` is a projected column and
    # legitimately contains "count".
    assert re.search(r"\bCOUNT\s*\(", query, re.IGNORECASE) is None
    assert 'FILTER(?transactionDate <= "2015-12-31"^^xsd:date)' in query
    assert recording_sparql.client.timeout == pytest.approx(3.0)
    assert recording_sparql.client.retry_attempts == 1


def test_probe_failure_is_not_retried(snapshot_routing, recording_sparql):
    from property_core.ppd_probe import ExistenceProbe

    recording_sparql.raise_on_call = RuntimeError("upstream down")
    probe = ExistenceProbe(client=recording_sparql.client)
    assert probe.older_records_exist(postcode="ZZ9 9ZZ", postcode_prefix=None,
                                     coverage_from="2016-01-01") is None
    assert len(recording_sparql.queries) == 1


def test_probe_is_not_issued_when_the_caller_gave_a_from_date(snapshot_routing,
                                                              probe_spy):
    """A caller who named a start date already knows what they excluded."""
    svc = PPDService()
    result = svc.search_transactions(postcode="ZZ9 9ZZ", postcode_prefix=None,
                                     from_date="2020-01-01", limit=10)
    assert result["count"] == 0
    assert probe_spy.calls == []
    assert result["provenance"].older_records_exist is None


def test_probe_is_not_issued_on_the_live_path(live_only, fake_live, probe_spy):
    """Without a snapshot there is no coverage boundary to probe across."""
    svc = PPDService()
    svc.search_transactions(postcode="ZZ9 9ZZ", postcode_prefix=None, limit=10)
    assert probe_spy.calls == []


def test_probe_geography_matches_the_request(snapshot_routing, probe_spy):
    probe_spy.result = False
    svc = PPDService()
    svc.search_transactions(postcode=None, postcode_prefix="ZZ9", limit=10)
    assert probe_spy.calls[0]["postcode_prefix"] == "ZZ9"
    assert probe_spy.calls[0]["coverage_from"] == "2016-01-01"
