# Snapshot image prerequisites — prepared, not deployed

Both Docker recipes install the optional `snapshot` extra unconditionally.
Snapshot serving remains disabled. Deploying and observing these dependencies
is a separate step from enabling the source, under G3 in the routing spec.

The extra contains DuckDB 1.5.5, zstandard 0.25.0 and botocore 1.43.83. The latter
supplies official request signing for the separately reviewed private-delivery
source. No required library dependency or existing pinned version changes.

No Fly configuration, worker count, Machine count, serving flag, version or
release changes. A locally built image is not evidence of deployment.

## Built-image evidence, 2026-08-31

Both images built on linux/amd64 from the dependency-only runtime tree. Each
imports all three dependencies above on Python 3.11.16. The floating
`python:3.11-slim` base resolved to manifest digest
`sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6`.
The development suite uses Python 3.11.13; do not conflate these patch versions.

Offline checks use a synthetic one-row tar.zst, never the actual PPD data:

- Flag off: real app lifespan starts and a transaction request returns the
  identifiable live fixture once, with SPARQL provenance.
- Healthy snapshot: real lifespan verifies, opens and serves the synthetic
  snapshot with snapshot provenance and zero live fixture calls.
- DuckDB blocked: typed `snapshot_extra_missing`, snapshot not routable, app
  remains available and serves the identifiable live fixture.
- zstandard blocked: extraction records `SnapshotExtraMissingError`, snapshot
  not routable, app remains available and serves the live fixture.

The API uses TestClient through its real lifespan and REST transactions route;
the app uses FastMCP's dispatcher after the entrypoint's registration imports.
Each mode runs in a fresh process; import blockers are self-checked. Containers
have networking disabled, one CPU and a 512 MiB limit. These are dependency and
fallback checks, not a full-size resource test or G1 pass.

No deployed observation is claimed. G3 remains incomplete until these images
are deployed and observed with the serving flag off. G1a, G1b and Stage 1 remain
separate requirements.
