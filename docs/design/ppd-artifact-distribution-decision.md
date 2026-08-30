# PPD snapshot artifact distribution — scope determination

**Owner:** Paul Boucherat
**Date:** 2026-08-29
**Status:** determined, for the scope below only
**Governs:** [`ppd-source-routing.md`](ppd-source-routing.md) §4.8 and the fourth
Royal Mail review trigger in §6

---

## What this is, and what it is not

This records **the owner's determination of permitted scope** for distributing
the PPD snapshot bundle. It is an operational decision by the party responsible
for this project, made under the existing HM Land Registry Open Government
Licence v3.0 terms and the posture already written into §6.

**It is not legal advice**, and it is not a legal opinion on the underlying
licence. Nothing here was produced by a qualified adviser, and it should not be
cited as though it were. Anyone relying on it should read it as what it is: the
owner deciding what this project will and will not do.

Three merged documents previously described distribution as an undecided
question — §4.8, the build runbook, and the changelog. This record exists so
that the decision is not silently re-litigated each time someone reads them.

---

## Determination

**Permitted:**

* **Private delivery of the snapshot bundle to project-controlled Fly Machines.**
* **Internal, read-only use for PPD price information** — matching a property to
  its sale history, and locating comparables, exactly as §6 already scopes the
  address fields.

**Not permitted, and unchanged by this determination:**

* **No public bundle download.** The bundle is never offered for download, to
  anyone, by any route.
* **No API, MCP or CLI surface serving bulk rows or the bundle.** §6's rule
  stands verbatim: no route serves the bundle or bulk rows, and no bulk or
  address export exists.
* **No address use outside price information** — no address validation, no
  autocomplete, no geocoding, no PAF-like lookup, no mailing lists, no
  address-derived product.
* **Attribution and provenance requirements are unchanged.** The required HM Land
  Registry statement, its placement rules, and the per-response
  `attribution_ref` pointer all continue to apply exactly as §6 specifies.

---

## This grants **no mutation authority**

Permission to distribute is **not** permission to build the distribution.
Specifically, this record authorises **none** of:

* creating a bucket, object store or any other cloud resource;
* uploading a bundle anywhere;
* creating or setting a Fly secret;
* configuring transport, credentials or access control;
* changing a Dockerfile, fly config, image, dependency or feature flag;
* deploying anything.

**Hosting, credentials, transport, retention and audit require their own written
design**, and that design requires its own mutation authorisation before any of
it is built. The design must state, at minimum: where the artifact is hosted and
under whose account; how a Machine authenticates to it; how long artifacts are
retained and what deletes them; what is audited and where those records go; and
what happens on failure — which must degrade to the live SPARQL source and never
to an unready service.

---

## Scope of the Royal Mail trigger this settles

§6 lists four triggers requiring separate Royal Mail review. **This determination
settles exactly one — redistribution of the snapshot bundle — for the scope
above.** The other three are untouched and still stop for review:

* raw or bulk export of address-bearing rows in any format;
* any endpoint returning address fields not tied to a price result;
* any non-price use — address validation, autocomplete, geocoding, PAF-like
  lookup.

Reading this record as clearance for any of those three would be a misreading.

---

## Re-review triggers

This determination is reopened, by the owner, on any of:

* **any change to the permitted scope** above, in either direction;
* **any new consumer of the bundle** — a service, a machine, a person or an
  environment not covered by "project-controlled Fly Machines";
* **any move toward public hosting**, including a bucket made public by default,
  a signed URL with a long or unbounded lifetime, or a CDN in front of the
  artifact;
* **any change to the HM Land Registry licence terms or Royal Mail's position**
  on address data in Price Paid Data;
* **any approach to the other three §6 triggers**;
* **the distribution implementation design** being written, which must be checked
  against this scope rather than assumed to fit it.
