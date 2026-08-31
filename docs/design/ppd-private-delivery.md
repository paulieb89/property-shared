# Private snapshot delivery — approved rollout implementation

Owner: Paul Boucherat. Approved in the rollout session on 2026-08-31.
Implements the permitted scope in `ppd-artifact-distribution-decision.md`;
does not relax the rev-8 routing specification or its rollout gates.

## Scope and account

A dedicated private Tigris bucket in the owner's Fly-linked `personal`
organisation. Dedicated name: `ppd-snapshots-20260831`. Confirm ownership
and non-existence before creation. Use the Tigris CLI authenticated through
Fly.io OAuth, not `fly storage create`: provisioning must not implicitly attach
credentials to either production app. Disable object ACL overrides and public
listing; anonymous reads must be rejected.

Initial artifact: `v20260828T194003Z`, 279109872 bytes,
SHA-256 `50f802b29d9802ee42319122214aeb0adc6761e96c4f6c9ddd0498500bb9072c`.
Upload only its bundle, immutable manifest and `current.json`, under `ppd/`.
Verify the remote bundle by a streamed read and SHA-256 before publishing the
pointer. Do not upload raw CSVs or the address-bearing query results.

## Authentication and transport

Use a distinct bucket-scoped publisher key and distinct bucket-scoped ReadOnly
keys for the two apps. No org-admin application credential. Never print secrets
or put them in code, build context, logs, URLs or Git. Application credentials
are installed explicitly as namespaced Fly secrets only at the delivery rollout
step; publishing credentials are never installed on an application.
Until that step, credentials are held in the owner's desktop secret store,
under service `ppd-snapshot/tigris`, never in a repo or scratch environment file.

The optional `snapshot` extra gains the official AWS `botocore` signing library.
It is lazy-loaded only when a Tigris source is selected. No handwritten signing
implementation, background key discovery or metadata-service credential lookup.
Use SigV4 Authorization headers, HTTPS and `https://t3.storage.dev`, region `auto`.
The source accepts validated bare object names, never a manifest-provided URL.
Reject redirects rather than forward credentials to another destination.

Use the existing streamed HTTP implementation and `read1` behaviour: bounded
control reads, incremental bundle hashing, byte-length check, socket timeout,
and total-download/stall detection retain their existing guarantees. No new
retry loop. Verification, safe extraction and the queryability gate are reused.

Configuration: `PPD_SNAPSHOT_S3_BUCKET`, `PPD_SNAPSHOT_S3_PREFIX` (default `ppd`),
`PPD_SNAPSHOT_S3_ACCESS_KEY_ID`, `PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY`. Refuse
ambiguous source selection. Missing configuration, rejected credentials,
unreachable storage or invalid bytes leave snapshot routing unavailable and the
server serving live, not empty successful results. No public bundle route.

## Retention and audit

Keep the initial artifact and pointer. Later immutable releases may be added by
the approved publisher; no automated deletion or lifecycle expiry in this first
rollout. Any cleanup is a separately reviewed operation; never delete the
currently advertised version or assume bucket deletion revokes credentials.
Machine-local retention remains one ephemeral materialization, per rev 8.

Record provider request IDs where available, object names, byte lengths,
digests, UTC timestamps, publishing actor, ACL/role checks and the deployed
image/Machine identities in sanitised ops evidence. Never claim complete
request-level access auditing unless actually available. Credential revocation
requires provider confirmation, not deletion of a local file.

## Verification and rollout sequence

1. Test signing, confinement, redirect rejection, bounded reads, timeout/error
   propagation and absent-extra failure against local fixtures; no PPD traffic.
2. Provision and verify private delivery; record actual role grants, anonymous
   rejection and positive authenticated reads. Publish the pointer last.
3. Build both images, smoke-test optional imports and failure-to-live semantics.
   Deploy and observe dependencies with snapshot serving off (G3). Provisioning
   and image preparation are independent; neither enables snapshot serving.
4. Measure actual boot on the target with serving disabled until G1a/G2/G3 pass.
   A control-only shadow mode must materialize without replacing live responses;
   do not enable the serving flag to work around the missing Stage 1 runner.
5. Complete Stage 1 and its artifact-bound Instance. Upstream 429/timeout is an
   inconclusive comparison, not a passing divergence check. Reuse the live
   result already being returned; do not double live queries on sampled calls.
6. Enable `property-shared` opt-in only after the gates pass. `propertydata`
   requires its separate G1b; passing G1a grants nothing for that app.

No volume, increased Machine count, worker change, widened concurrency limit,
hot refresh, public hosting or new PPD request semantics are introduced here.
