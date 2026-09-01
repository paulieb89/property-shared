"""Built-image check with synthetic data; never contacts PPD or uses credentials."""
import hashlib
import importlib.abc
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

# Match uvicorn's default app-dir insertion. This script is mounted at /check.py
# while the API image intentionally runs its copied source tree from /app.
sys.path.insert(0, os.getcwd())


def fixture(root):
    import duckdb
    import zstandard
    from property_core.snapshot.schema import REQUIRED_COLUMNS
    directory = root / "year=2026"
    directory.mkdir()
    values = {"transaction_id": "SYNTHETIC", "postcode": "B5 7AA",
              "outcode": "B5", "sector": "B5 7", "price": 100000,
              "transfer_date": "2026-06-01", "property_type": "F",
              "duration": "L", "ppd_category": "A", "new_build": False}
    columns, parameters = [], []
    for name, types in REQUIRED_COLUMNS.items():
        columns.append(f"CAST(? AS {sorted(types)[0]}) AS {name}")
        parameters.append(values.get(name))
    con = duckdb.connect()
    con.execute("CREATE TABLE fixture AS SELECT " + ",".join(columns), parameters)
    con.execute(f"COPY fixture TO '{directory / 'data.parquet'}' (FORMAT PARQUET)")
    con.close()
    tar = root / "fixture.tar"
    with tarfile.open(tar, "w") as archive:
        archive.add(directory / "data.parquet", arcname="year=2026/data.parquet")
    blob = zstandard.ZstdCompressor().compress(tar.read_bytes())
    (root / "fixture.tar.zst").write_bytes(blob)
    manifest = dict(snapshot_version="synthetic-v1", bundle_object="fixture.tar.zst",
                    bundle_sha256=hashlib.sha256(blob).hexdigest(), bundle_bytes=len(blob),
                    parquet_files=1, rows=1, coverage_from="2016-01-01",
                    coverage_to="2026-06-30", provisional_from="2026-03-01",
                    layout="year", duckdb_version=duckdb.__version__)
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "current.json").write_text(json.dumps({"current_manifest": "manifest.json"}))


def stage1(target):
    """Invoke the Stage 1 comparator inside the built image, flag off.

    Reading the Dockerfile proves nothing about whether the files landed, the
    package imports on this platform, or the CLI wires up -- and the one thing
    that must hold on a serving image is that the comparator does NOTHING
    unless it is deliberately enabled. So this actually runs it.

    Only the API image carries the comparator; `propertydata` is out of Stage 1
    scope and must not have gained it.
    """
    root = Path(os.getcwd())
    present = (root / "tools" / "ppd_snapshot" / "stage1_shadow.py").is_file()
    if target != "api":
        assert not present, (
            "the propertydata image carries the Stage 1 comparator; Stage 1 is "
            "property-shared only and propertydata must stay untouched")
        print(json.dumps({"image": target, "mode": "stage1", "passed": True,
                          "comparator_present": False}))
        return
    assert present, "the API image does not carry tools/ppd_snapshot/stage1_shadow.py"

    helped = subprocess.run(
        [sys.executable, "-m", "tools.ppd_snapshot.stage1_shadow", "--help"],
        capture_output=True, text=True, cwd=root)
    assert helped.returncode == 0, helped.stderr
    assert "qualify" in helped.stdout and "compare" in helped.stdout, helped.stdout

    # Default off: with the flag absent it must refuse, exit 2, and never reach
    # an adapter -- even though this image has DuckDB installed and the app on
    # this Machine may well have a snapshot materialized.
    environment = {k: v for k, v in os.environ.items()
                   if k != "PPD_SHADOW_COMPARE_ENABLED"}
    for argv in (["qualify", "--out", "/tmp/should-not-exist.json"],
                 ["compare", "--instance", "/tmp/nope.json",
                  "--report", "/tmp/should-not-exist.json"]):
        refused = subprocess.run(
            [sys.executable, "-m", "tools.ppd_snapshot.stage1_shadow", *argv],
            capture_output=True, text=True, cwd=root, env=environment)
        assert refused.returncode == 2, (argv, refused.returncode, refused.stdout,
                                         refused.stderr)
        assert "refused" in refused.stdout, refused.stdout
        assert "PPD_SHADOW_COMPARE_ENABLED" in refused.stdout, refused.stdout
    assert not Path("/tmp/should-not-exist.json").exists(), (
        "a refused invocation still wrote its output file")

    print(json.dumps({"image": target, "mode": "stage1", "passed": True,
                      "comparator_present": True, "default_off_exit_code": 2}))


def child(root, mode, target):
    blocked = mode if mode in {"duckdb", "zstandard", "botocore"} else None
    if blocked:
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, *args):
                if fullname == blocked or fullname.startswith(blocked + "."):
                    raise ModuleNotFoundError("blocked " + blocked)
        sys.meta_path.insert(0, Block())
        try:
            __import__(blocked)
        except ModuleNotFoundError:
            pass
        else:
            raise AssertionError("blocker inactive")
    os.environ["PPD_SNAPSHOT_ENABLED"] = "0" if mode == "off" else "1"
    os.environ["PPD_SNAPSHOT_CACHE_DIR"] = str(root / ("store-" + mode))
    os.environ["PPD_SNAPSHOT_DIR"] = str(root)
    if mode == "botocore":
        os.environ.pop("PPD_SNAPSHOT_DIR")
        os.environ["PPD_SNAPSHOT_S3_BUCKET"] = "ppd-test"
        os.environ["PPD_SNAPSHOT_S3_ACCESS_KEY_ID"] = "fake-key"
        os.environ["PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY"] = "fake-secret"

    # Prove live fallback with an identifiable result, not a quiet empty reply.
    from property_core.ppd_client import PricePaidDataClient, SearchPage
    from property_core.models.ppd import PPDTransaction
    from property_core.provenance import TransportEvidence
    from property_core.snapshot import bootstrap
    live_calls = []
    def fake_live(self, **kwargs):
        live_calls.append(kwargs)
        return SearchPage(transactions=[PPDTransaction(transaction_id="LIVE-FIXTURE",
                          postcode="B5 7AA", date="2026-06-01", price=100000)],
                          evidence=TransportEvidence(raw_bindings_returned=1, fetch_limit=10))
    PricePaidDataClient.search_with_evidence = fake_live

    # Capture the exact missing-package error at the materialization boundary;
    # normal bootstrap still handles it and the actual app lifespan continues.
    failures = []
    original = bootstrap._materialize
    def record_failure():
        try:
            return original()
        except Exception as exc:
            failures.append(exc)
            raise
    bootstrap._materialize = record_failure
    boot_warnings = []
    class Capture(logging.Handler):
        def emit(self, record):
            boot_warnings.append(record.getMessage())
    logging.getLogger("property_core.snapshot.boot").addHandler(Capture())

    def check(payload):
        snapshot = mode == "healthy"
        assert bootstrap.snapshot_status()["routable"] is snapshot
        assert payload["count"] == 1
        assert payload["provenance"]["source"] == ("snapshot" if snapshot else "sparql")
        assert len(live_calls) == (0 if snapshot else 1), live_calls

    if target == "api":
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            assert client.get("/v1/health").status_code == 200
            result = client.get("/v1/ppd/transactions", params={"postcode": "B5 7AA"})
            assert result.status_code == 200, result.text
            check(result.json())
    else:
        import anyio
        from fastmcp import Client
        from property_app.server import mcp
        # Registration is performed by the deployed property-app entrypoint.
        from property_app import tools
        from property_app.dashboards import comps, listings, rental, unified, yield_view
        async def run():
            async with Client(mcp) as client:
                result = await client.call_tool("ppd_transactions", {"postcode": "B5 7AA"})
                assert not result.is_error
                check(result.structured_content)
        anyio.run(run)

    if blocked == "zstandard":
        # Runtime records extraction failure in its BootReport rather than raising.
        assert any("SnapshotExtraMissingError" in m and "zstandard" in m for m in boot_warnings), boot_warnings
    elif blocked:
        assert len(failures) == 1, failures
        assert failures[0].code == "snapshot_extra_missing"
        assert failures[0].package == blocked
    else:
        assert not failures, failures
    print(json.dumps({"image": target, "mode": mode, "passed": True,
                      "live_fixture_calls": len(live_calls)}))


if __name__ == "__main__":
    if sys.argv[1] == "child":
        child(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "stage1":
        stage1(sys.argv[2])
    else:
        import duckdb, zstandard, botocore
        print(json.dumps({"python": sys.version.split()[0], "duckdb": duckdb.__version__,
                          "zstandard": zstandard.__version__, "botocore": botocore.__version__}), flush=True)
        with tempfile.TemporaryDirectory(prefix="ppd-image-smoke-") as temp:
            root = Path(temp)
            fixture(root)
            modes = ("off", "healthy", "duckdb", "zstandard")
            if sys.argv[2:] == ["include-private"]:
                modes += ("botocore",)
            for mode in modes:
                subprocess.run([sys.executable, __file__, "child", str(root), mode, sys.argv[1]],
                               check=True)
