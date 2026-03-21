---
paths:
  - "tests/**"
---

# Test Rules

## Live Test Gating

Tests making real network calls MUST be gated:

```python
@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1")
def test_something_live() -> None:
    ...
```

## Graceful Failure

Skip on upstream errors — don't let CI fail because Land Registry returned 503:

```python
except urllib.error.HTTPError as exc:
    pytest.skip(f"Endpoint unavailable: {exc}")
```

## Pure Unit Tests

Deterministic tests (stamp duty calculator, address parsing) need no gating — they don't hit the network.

## Naming

- Files: `test_*.py`
- Functions: `test_*`
- Use `pytest.mark.anyio` for async tests

## Credential-Dependent Tests

Skip when credentials are missing (EPC, Companies House):

```python
@pytest.mark.skipif(not os.getenv("EPC_API_KEY"), reason="EPC credentials not set")
```

## Reference

- Pure unit tests: `tests/test_stamp_duty.py`
- Live gated tests: `tests/test_ppd_service_live.py`
