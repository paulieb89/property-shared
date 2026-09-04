# Release and snapshot-refresh runbook

Two operations, deliberately independent. Confusing them is the main way this
goes wrong.

| | Changes | Needs a version bump | Needs a deploy |
|---|---|---|---|
| **Code release** | the image both apps run | yes | yes |
| **Snapshot refresh** | which PPD data is served | no | no |

A refresh publishes a new artifact and moves one pointer. It does not touch the
image, the app version or PyPI. See "the coupling to remove" at the end — one
constant currently breaks that separation.

## What is public in this document, and what must never be

This repository is public and `docs/ops/` already names the bucket, the key
labels, their fingerprint prefixes and Machine IDs. That is deliberate and safe:
the bucket is `IsPublic=false` so its name grants nothing, a key *label* is not a
key, and a SHA-256 prefix of a key id is not the id.

**Never in this or any repo file:** access key ids, secret access keys, Fly
tokens, OAuth tokens, the contents of `.env`. Credentials live in the owner's
desktop secret store and reach a process from there, never through a file, an
environment file, a build context or a command line.

---

## A. Code release

1. **Bump the version in three places.** They must agree or the reconcile job
   fails the release before it deploys anything:
   - `pyproject.toml` `version`
   - `server.json` `version`
   - `server.json` `packages[0].version`
2. **Regenerate the lockfile** — `uv lock`. `scripts/validate.sh` runs
   `uv lock --check` first and refuses otherwise.
3. **Write the CHANGELOG entry.** Breaking changes go in a
   `### Breaking Changes` section within a minor bump; this repo does not force
   a major bump for them.
4. **Open a PR, review, merge.**
5. **Publish a GitHub Release** on the merged commit:

   ```
   gh release create vX.Y.Z --title "vX.Y.Z — <summary>" --notes-file <notes>
   ```

   Release notes have historically been the CHANGELOG entry body. Tags are
   lightweight, so `--notes-from-tag` publishes nothing — do not use it.

**Publish the Release; never `fly deploy` locally.** `fly deploy` ships the
working directory, not a commit. `release.yml` does `actions/checkout@v4` and
deploys the tag, which is the only way to know what shipped.

The workflow then runs: validate → PyPI → both Fly deploys in parallel →
reconcile. The deploys retry with `--depot=false` after a Depot builder failure
(v1.15.1 lost an hour to one). The reconcile job polls both apps for the released
version and needs two consecutive agreeing rounds; **a reconcile failure means
the apps disagree**, which is the silent state it exists to catch.

---

## B. Snapshot refresh

### Cadence

HM Land Registry publishes `pp-complete.csv` monthly, around the 28th. The
coverage end a release implies is the **first of the publication month minus one
day** — a file published 28 August covers to 31 July.

`FRESHNESS_WARNING_DAYS = 45`, so a **monthly refresh keeps the artifact
permanently inside the freshness threshold**. Skip a month and the warning fires
by itself, in every response's provenance. The threshold is the reminder; it does
not need a calendar.

Registration lag is separate and much longer. Measured 2026-09-04 on the
full-history artifact: the most recent covered month held **29%** of a typical
month's sales, and months six back still only ~58%. Recent data is thin because
it does not exist yet, not because the snapshot is stale.

### Procedure

```bash
# 1. Has HMLR published? HEAD only, nothing downloaded.
uv run --extra snapshot python -m tools.ppd_snapshot check-release \
    --state ~/ppd-snapshot/release-state.json

# 2. Fetch and digest in one pass (evidence: "streamed-download"). ~11 min.
uv run --extra snapshot python -m tools.ppd_snapshot download \
    --dest ~/ppd-snapshot/pp-complete.csv --receipt ~/ppd-snapshot/receipt.json

# 3. Build, validate, package, verify, boot, promote. --coverage-to must equal
#    the coverage end the bound release implies, or it refuses before writing.
uv run --extra snapshot python -m tools.ppd_snapshot all \
    --csv ~/ppd-snapshot/pp-complete.csv \
    --work ~/ppd-snapshot/work --dist ~/ppd-snapshot/dist \
    --coverage-to <end of prior month> \
    --release-state ~/ppd-snapshot/release-state.json \
    --source-receipt ~/ppd-snapshot/receipt.json --memory 4GB

# 4. Offline verification of what was built. No upstream needed.
uv run --extra snapshot python -m tools.ppd_snapshot.nonlive_verify \
    --snapshot-dir ~/ppd-snapshot/work/boot-cache/snapshots/<version> \
    --report ~/ppd-snapshot/nonlive-<version>.json
```

`--work` and `--dist` must be on one filesystem. Version names are immutable: a
rebuild takes a new `v<timestamp>Z`, and a same-version/different-digest bundle
fails closed at boot.

### Publishing to Tigris

Bucket `ppd-snapshots-20260831`, prefix `ppd/`, endpoint `https://t3.storage.dev`.

Three keys, one bucket role each, in the owner's desktop secret store under
service `ppd-snapshot/tigris`:

| Entry | Role | `sha256(id)` prefix |
|---|---|---|
| `ppd-publisher-20260831` | Editor — publishing | `28f0cfb23ca7` |
| `ppd-property-shared-20260831` | ReadOnly — on the app | `054715071f55` |
| `ppd-propertydata-20260831` | ReadOnly | `5d43733c3a1e` |

Each entry's value is JSON carrying `id`, `secret`, `bucket` and `name`. **Check
the fingerprint before publishing.** A ReadOnly key fails the first PUT with a
403 that is indistinguishable from a signing error, which is the one genuinely
confusing failure here.

**Order is the whole safety property:**

1. Upload the bundle **as a multipart upload**
2. **GET it back and verify** sha256 and byte length — catches a truncated upload
3. PUT the manifest
4. PUT `current.json` **last**

`current.json` is the single control point; every Machine reads it on next boot.
Stop at any point before step 4 and nothing has changed for anyone, because it
still names the previous manifest. This is not theoretical: on 2026-09-04 the
first publish attempt failed at step 1 after 8.5 minutes of transfer, and
production was untouched.

**The bundle must go up as multipart, not a single PUT.** A single PUT of the
1.19 GB bundle was rejected with `XAmzContentSHA256Mismatch` after transferring
the whole object — the server received a complete request whose body hashed
differently from the signed header. Small objects sign and upload fine by either
route, so the fault is in streaming a very large body as one request.

Multipart is what S3 clients do above ~100 MB anyway, and it is better here for
a reason beyond working: each part carries its own sha256 and is rejected on
arrival, so a corrupt transfer fails on the offending part in seconds instead of
at the end of the whole object. 64 MiB parts; S3's minimum is 5 MiB except for
the last. Abort the upload id if any part fails, or the incomplete upload lingers
and is billed.

Manifest and `current.json` are small enough for a single PUT.

### Activating

```
fly machine restart <machine id> -a property-shared
```

There is no hot refresh — activation is at process start only. `/tmp` is
ephemeral, so the Machine re-materializes the artifact: ~150 s for a 1.19 GB
bundle at the measured 63.6 Mbit/s. Boot is non-blocking, so the app is ready in
~10 s and serves the live source meanwhile — which, while that source is
degraded, means PPD data is briefly unavailable rather than merely stale.

Confirm with `/v1/meta`: `routable: true`, and `coverage_from`/`coverage_to`
showing the new window.

**Rollback** is `current.json` back to the previous manifest plus a restart. The
snapshot is derived and disposable; there is no migration.

---

## The coupling to remove

`tools/ppd_snapshot/boot_only_verify.py` hardcodes `EXPECTED_BUNDLE_BYTES` and
the review that created it deliberately made it non-overridable from the CLI. So
every new artifact makes that verifier report `cold_run_valid: false` until
someone edits a constant and ships an image — dragging a code release into every
snapshot refresh, which is exactly the separation this runbook opens with.

It affects only the out-of-band verifier, never the serving path, so nothing is
blocked. It should be derived from the manifest rather than pinned.

A **Fly Volume** would also remove the ~150 s re-materialization: the boot path
already reuses an existing materialization when the digest matches, and
`PPD_SNAPSHOT_CACHE_DIR` is configurable. The specification currently states that
neither app declares a Volume, and G1a was measured on ephemeral rootfs, so that
assumption changes with it.
