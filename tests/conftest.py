"""Shared test fixtures.

The EPC credential fixtures exist because `EPCClient(token=None)` does NOT mean
"unconfigured" — the constructor falls back to `os.getenv("EPC_API_TOKEN")`, so a
token in the ambient environment silently reconfigures the client and any test
asserting unconfigured behaviour passes or fails depending on the developer's
shell and whether a .env happens to exist.
"""

from __future__ import annotations

import pytest

EPC_CREDENTIAL_VARS = ("EPC_API_TOKEN", "EPC_API_EMAIL", "EPC_API_KEY")


@pytest.fixture
def no_epc_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee an unconfigured EPC environment for the duration of a test.

    Removes every EPC credential variable, so a test asserting unconfigured
    behaviour is deterministic whether or not the developer exports credentials
    or keeps a .env. monkeypatch restores the previous values afterwards.
    """
    for var in EPC_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
