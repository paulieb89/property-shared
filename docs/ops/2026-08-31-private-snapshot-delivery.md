# Private snapshot delivery — 2026-08-31

Status: private artifact published and read-verified; production not changed.
Implements [the approved delivery design](../design/ppd-private-delivery.md).
This is not a G1 or Stage 1 pass and does not authorise snapshot serving.

## Provisioning and credentials

Tigris CLI 3.10.0, authenticated to the owner's Fly-linked personal organisation,
created `ppd-snapshots-20260831` with private access at 02:10:53Z.
No `fly storage create` was used. Both apps' secret names and digests were
compared before/after creation and were unchanged. No application credentials
have been installed in Fly by this rollout session.

Three active keys have one bucket role each, verified through the provider:

| Desktop secret-store entry | Role | SHA-256 ID fingerprint prefix |
| --- | --- | --- |
| ppd-publisher-20260831 | Editor | 28f0cfb23ca7 |
| ppd-property-shared-20260831 | ReadOnly | 054715071f55 |
| ppd-propertydata-20260831 | ReadOnly | 5d43733c3a1e |

Service: `ppd-snapshot/tigris`. Values are in the owner's desktop secret store,
not Git, environment files or build context. No publisher key belongs on an app.

Policy status returned `IsPublic=false`; object ACL overrides are disabled.
The ACL grants FULL_CONTROL to the owner and the exact Tigris organisation-admin
group `https://groups.tigris.dev/org/admins`, not AllUsers or AuthenticatedUsers.
The first inspection incorrectly rejected every group URI; the actual grantee
was then inspected, not assumed public. This organisation-admin group is also
shown in [Tigris's provider-authored ACL explanation](https://dev.to/tigrisdata/sharing-files-with-the-model-context-protocol-178e).

## Published objects

Only these objects exist under `ppd/`. The bundle was fully read through the
property-shared ReadOnly key and SHA-256 checked before the manifest and pointer
were published. Each object's anonymous GET returned 403 after its authenticated
read succeeded. The propertydata ReadOnly key separately read the manifest.

| Object | Bytes | SHA-256 | Readback request ID |
| --- | ---: | --- | --- |
| snapshot-v20260828T194003Z.tar.zst | 279109872 | 50f802b29d9802ee42319122214aeb0adc6761e96c4f6c9ddd0498500bb9072c | 1788143473792276247 |
| manifest-v20260828T194003Z.json | 412 | 2e01062317e477b407f2fc0683744c2a135d11e6e7169471d5666634d307715f | 1788143507150342352 |
| current.json | 60 | acfb96adf8231421564e4a45bb3ed711568fd0e251ed2b7f1b231ea2c3aa0abf | 1788143507821544456 |

The first upload's verification script used `iter_chunks` on the raw response
returned by the body context manager and failed. The bundle had been written;
neither manifest nor pointer had. The corrected checker streamed `read(size)`,
verified the existing bundle without overwriting it, then published the two
missing objects. No raw CSV, build report or query result was uploaded.
These request IDs are individual observations, not complete access auditing.

## Real-source local acceptance

The new signed source fetched the pointer and manifest successfully. One full
boot from Tigris through SnapshotRuntime and SnapshotAdapter downloaded exactly
279109872 bytes, verified the digest and opened the 10,394,935-row snapshot.
A 20-row B5 district query returned only B5 outcodes.

- Local laptop cold boot plus adapter validation: 33.417 seconds.
- Subsequent query: 28.665 ms.
- Process peak RSS: 263192 KiB, not an app-process or Machine total.
- Runtime total: 33267.4 ms. No Land Registry request was made.

This does not satisfy the 30-second Fly readiness gate. It includes the actual
private transport, but neither Fly's network nor its filesystem or app lifespan.
Do not substitute this figure for G1a/G1b or for Stage 1 traffic evidence.

## Next boundary

The dependency-only image change must be reviewed, deployed and observed with
the serving flag off. Private-source code is a separate change on top of it.
Real G1a/G1b measurements and the missing production shadow runner remain ahead;
no serving enablement, Volume, scale, concurrency or worker change occurred.
