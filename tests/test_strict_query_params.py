"""An unknown query parameter is refused, not discarded.

FastAPI ignores query parameters it does not declare. That is a reasonable HTTP
default and a bad one for this API, because the parameters people get wrong are
the ones that bound the answer:

    GET /v1/ppd/transactions?postcode=NG11+9HD&months=24

`months` does not exist on that route — it takes `from_date`/`to_date`. The
request succeeded, silently scanned the whole eleven-year window instead of two
years, and returned a plausible answer to a question nobody asked. It took 1.7 s
instead of 0.27 s, and nothing anywhere said the filter had been dropped.

That is worse than an error. An error is recoverable; a plausible wrong answer
is not, and a model has no way to notice. So this is an intentional breaking
change: requests that "succeeded" while carrying a typo now fail loudly, with
the offending name and the accepted alternatives.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


# --- the reproduced case ----------------------------------------------------


def test_the_months_typo_that_started_this_is_now_refused(client):
    r = client.get("/v1/ppd/transactions",
                   params={"postcode": "NG11 9HD", "months": 24})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "months" in detail["unknown"]
    assert "from_date" in detail["supported"] and "to_date" in detail["supported"]


def test_a_misspelling_is_refused_and_the_intended_name_suggested(client):
    """`form_date` silently did nothing. Naming the near-miss is the whole point."""
    r = client.get("/v1/ppd/transactions",
                   params={"postcode": "NG11 9HD", "form_date": "2024-01-01"})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "form_date" in detail["unknown"]
    assert detail["did_you_mean"].get("form_date") == "from_date"


def test_every_unknown_parameter_is_named_not_just_the_first(client):
    r = client.get("/v1/ppd/transactions",
                   params={"postcode": "NG11 9HD", "months": 24, "wibble": 1})
    assert r.status_code == 400
    assert set(r.json()["detail"]["unknown"]) == {"months", "wibble"}


def test_the_error_is_400_and_typed(client):
    """400: the request itself is malformed, distinct from 422 for a bad value."""
    r = client.get("/v1/ppd/transactions", params={"postcode": "NG11 9HD", "x": 1})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_query_parameter"


# --- and it must not break anything that was already correct ----------------


@pytest.mark.parametrize(
    "path, params",
    [
        ("/v1/ppd/transactions", {"postcode": "NG11 9HD", "from_date": "2024-01-01"}),
        ("/v1/ppd/transactions", {"postcode": "NG11 9HD", "limit": 5}),
        ("/v1/health", {}),
        ("/v1/meta", {}),
        ("/v1/calc/stamp-duty", {"price": 300000}),
    ],
)
def test_declared_parameters_are_still_accepted(client, path, params):
    """A valid request must not become a 400. Upstream failures are fine here."""
    r = client.get(path, params=params)
    assert r.status_code != 400, r.text


def test_a_route_with_no_query_parameters_still_refuses_an_unknown_one(client):
    r = client.get("/v1/health", params={"nonsense": 1})
    assert r.status_code == 400
    assert "nonsense" in r.json()["detail"]["unknown"]


def test_a_path_parameter_is_not_mistaken_for_an_unknown_query_parameter(client):
    """Path params never appear in the query string; guard against over-reach."""
    r = client.get("/v1/ppd/transaction/abc")
    assert r.status_code != 400 or "unknown_query_parameter" not in r.text


def test_repeated_values_for_a_declared_parameter_are_accepted(client):
    r = client.get("/v1/ppd/transactions",
                   params=[("postcode", "NG11 9HD"), ("limit", 5), ("limit", 6)])
    assert r.status_code != 400, r.text


# --- a mixture must fail whole, not partially execute -----------------------


def test_a_valid_parameter_alongside_an_invalid_one_still_fails(client):
    """Rejection is whole-request. A 400 that had already queried upstream would
    be the worst of both: the caller sees an error and the work happened anyway.
    """
    with patch("property_core.ppd_service.PPDService.search_transactions") as service:
        r = client.get("/v1/ppd/transactions",
                       params={"postcode": "NG11 9HD", "from_date": "2024-01-01",
                               "months": 24})
    assert r.status_code == 400
    assert service.call_count == 0, (
        "the handler ran despite the request being refused; rejection must "
        "happen before any upstream or snapshot work"
    )


def test_the_valid_parameters_are_still_listed_as_supported(client):
    """The caller must be able to see which of their parameters was the problem."""
    r = client.get("/v1/ppd/transactions",
                   params={"postcode": "NG11 9HD", "from_date": "2024-01-01",
                           "months": 24})
    detail = r.json()["detail"]
    assert detail["unknown"] == ["months"]
    assert {"postcode", "from_date"} <= set(detail["supported"])


# --- the machine-readable contract ------------------------------------------


def test_the_error_body_is_machine_readable_not_only_prose(client):
    """Prose helps a human and an LLM; it must not be the only contract.

    A client keying off the sentence breaks when the sentence improves, so the
    stable surface is the codes and lists.
    """
    r = client.get("/v1/ppd/transactions", params={"postcode": "NG11 9HD", "zzz": 1})
    detail = r.json()["detail"]

    assert detail["error"] == "unknown_query_parameter"
    assert isinstance(detail["unknown"], list) and detail["unknown"] == ["zzz"]
    assert isinstance(detail["supported"], list) and detail["supported"]
    assert isinstance(detail["did_you_mean"], dict)
    assert detail["retryable"] is False
    assert isinstance(detail["detail"], str) and detail["detail"]


def test_did_you_mean_is_present_but_empty_when_nothing_is_close(client):
    """Always the same type. An absent key would make consumers branch on shape."""
    r = client.get("/v1/ppd/transactions",
                   params={"postcode": "NG11 9HD", "zzzzzzzz": 1})
    assert r.json()["detail"]["did_you_mean"] == {}


def test_an_unrelated_name_is_not_given_a_confident_wrong_suggestion(client):
    """A wrong suggestion is its own plausible-but-wrong answer."""
    r = client.get("/v1/ppd/transactions", params={"postcode": "NG11 9HD", "colour": 1})
    assert "colour" not in r.json()["detail"]["did_you_mean"]
