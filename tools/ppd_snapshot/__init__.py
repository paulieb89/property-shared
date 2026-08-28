"""Local build and validation pipeline for the PPD snapshot.

**Local only.** Nothing here uploads, publishes, creates a bucket, reads a
secret or touches a deployed system: governing specification section 4.8 limits
this stage to building and validating an artifact on a workstation, and artifact
distribution is a separately approved decision.

Deliberately outside the published wheel (`[tool.hatch.build.targets.wheel]`
lists `property_core`, `app`, `property_cli`, `property_app` and not this
package): the pipeline needs DuckDB and a 5.5 GB CSV, and no library consumer
should carry either.

The division of labour with `property_core.snapshot` is the point of the design:
this package *declares* what it built, and the merged runtime -- fetch, digest
verification, member-validated extraction, activation, then
`SnapshotAdapter.open` -- is what *judges* it. Validation here re-uses the
repository's own contracts (`property_core.snapshot.schema.REQUIRED_COLUMNS`,
`SnapshotManifest`) rather than restating them, so the build cannot drift from
the thing that has to read it.
"""
