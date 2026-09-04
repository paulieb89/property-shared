"""PPD domain service: orchestration over the typed transport client.

The transport client (PricePaidDataClient) now returns typed Pydantic models
directly. This service layer handles guardrails, search-level prefix logic,
stats computation, and subject-property matching. Sync throughout.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, median, quantiles
from typing import Any, Dict, List, Optional

from property_core.exceptions import InvalidPostcodeError, SnapshotFailure
from property_core.models.ppd import (
    PPDCompsQuery,
    PPDCompsResponse,
    PPDTransaction,
    SubjectProperty,
)
from property_core.ppd_client import PricePaidDataClient
from property_core.window import window_from_months
from property_core.ppd_source import (
    CoveragePolicy,
    active_adapter,
    fallback_warning,
    live_provenance,
    resolve_coverage,
    snapshot_provenance,
    validate_date_range,
)
from property_core.provenance import SourceKind

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
FORM_MAX_LIMIT = 50

# Residential property type codes used for the default comps() residential filter.
# F=Flat, D=Detached, S=Semi, T=Terraced. O=Other (commercial/non-standard) is excluded
# unless the caller opts in via property_type="O" or property_type="ALL".
_RESIDENTIAL_TYPES = {"F", "D", "S", "T"}

# Sentinel for property_type meaning "no filter at all" — the raw firehose.
_PROPERTY_TYPE_ALL = "ALL"


class PPDService:
    """Domain service for PPD operations.

    Orchestrates PricePaidDataClient (which returns typed models) and adds
    guardrails, stats computation, and subject-property matching.
    All methods are synchronous.
    """
    def __init__(self, client: Optional[PricePaidDataClient] = None,
                 adapter: Optional[Any] = None):
        self.client = client or PricePaidDataClient()
        #: An explicit adapter overrides process state; `None` means "ask the
        #: process at call time". Resolved per call rather than per instance
        #: because the routers construct one service at import, long before boot.
        self._adapter_override = adapter

    def _active_adapter(self) -> Optional[Any]:
        """The snapshot adapter to route to, or None for the live source."""
        if self._adapter_override is not None:
            return self._adapter_override
        return active_adapter()

    def download_url(
        self,
        *,
        kind: str,
        year: Optional[int],
        part: Optional[int],
        fmt: str,
    ) -> str:
        """Resolve download URL for bulk PPD datasets. Returns the URL string."""
        if kind == "complete":
            return self.client.complete_url(fmt=fmt)
        elif kind == "monthly":
            return self.client.monthly_change_url(fmt=fmt)
        elif kind == "year":
            if year is None:
                raise ValueError("year is required when kind=year")
            return self.client.year_url(year, part=part, fmt=fmt)
        else:
            raise ValueError("kind must be one of: complete, monthly, year")

    def search_transactions(
        self,
        *,
        postcode: Optional[str],
        postcode_prefix: Optional[str],
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        property_type: Optional[str] = None,
        estate_type: Optional[str] = None,
        transaction_category: Optional[str] = None,
        record_status: Optional[str] = None,
        new_build: Optional[bool] = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        order_desc: bool = True,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Search PPD transactions, from the snapshot when one is routable.

        Returns a dict with keys: count, limit, offset, results, warnings, raw,
        provenance.

        This surface takes explicit dates, so it uses the EXPLICIT coverage
        policy: a `from_date` before `coverage_from` is refused with
        `PPDCoverageError` rather than answered partially. An absent `from_date`
        means "all time" on the live source and "coverage" here, so it is
        narrowed with a warning rather than silently.

        When the window was narrowed and the result is empty, one bounded
        existence probe runs against the live source (spec 2.4): an empty list
        from a dateless call otherwise reads as "never sold", which is a
        confident false claim.
        """
        warnings: List[str] = []

        # Before routing, so neither source is queried on input that cannot mean
        # anything -- and so the same bad input gets the same typed answer
        # whichever source would have served it.
        validate_date_range(from_date, to_date)

        if limit <= 0:
            limit = DEFAULT_LIMIT
        if limit > MAX_LIMIT:
            warnings.append(f"limit capped to {MAX_LIMIT}")
            limit = MAX_LIMIT
        if offset > 0:
            # The upstream ordering is not guaranteed total across pages, so a
            # deep offset can repeat or omit rows. Keyset paging is the correct
            # mechanism; introducing it is out of scope here.
            warnings.append(
                "offset pagination is unstable and incomplete: results may repeat "
                "or omit rows across pages"
            )

        if record_status is not None:
            # Rejected before any routing decision, so the snapshot path has
            # exactly the live path's behaviour (spec test 19). Raised by the
            # client normally; done here because the snapshot path never calls it.
            from property_core.ppd_client import (
                RECORD_STATUS_UNSUPPORTED,
                UnsupportedRecordStatusFilterError,
            )

            raise UnsupportedRecordStatusFilterError(RECORD_STATUS_UNSUPPORTED)

        adapter = self._active_adapter()
        if adapter is not None:
            try:
                # Inside the try on purpose. `resolve_coverage` can raise a
                # SnapshotCoverageGapError, which belongs to the fallback
                # taxonomy; PPDCoverageError and InvalidPostcodeError do not
                # subclass SnapshotFailure and so still reach the caller, which
                # is the point -- retrying either against live would hide the
                # fact the caller needs.
                decision = resolve_coverage(
                    adapter, from_date=from_date, to_date=to_date,
                    policy=CoveragePolicy.EXPLICIT)
                page = adapter.search(
                    postcode=postcode,
                    postcode_prefix=postcode_prefix,
                    from_date=decision.from_date,
                    to_date=decision.to_date,
                    min_price=min_price,
                    max_price=max_price,
                    property_types={property_type} if property_type else None,
                    estate_type=estate_type,
                    transaction_category=transaction_category,
                    new_build=new_build,
                    limit=limit,
                    offset=offset,
                    order_desc=order_desc,
                )
            except SnapshotFailure as exc:
                warnings.append(fallback_warning(exc))
            else:
                results = page.transactions
                warnings.extend(decision.warnings)
                older = None
                # `from_narrowed`, NOT `narrowed`: the probe asks whether
                # anything exists BEFORE coverage begins, which is only a
                # question for a caller who did not choose the lower bound. A
                # caller who named `from_date` already excluded that period
                # deliberately, and an upstream request to tell them so is noise.
                if (not results and decision.from_narrowed and offset == 0
                        and adapter.coverage_from):
                    # No probe when there ARE rows: the question is already
                    # answered, and a probe would be a second upstream call
                    # for nothing (spec test 13).
                    older = self._probe_older_records(
                        postcode=postcode, postcode_prefix=postcode_prefix,
                        coverage_from=adapter.coverage_from)
                    warnings.extend(_older_records_warnings(
                        older, adapter.coverage_from, adapter.coverage_to))

                return {
                    "count": len(results),
                    "limit": limit,
                    "offset": offset,
                    "results": results,
                    "warnings": warnings,
                    "raw": [t.raw for t in results] if include_raw else None,
                    "provenance": snapshot_provenance(
                        adapter, decision=decision, sample_count=len(results),
                        sample_limit=limit, offset=offset,
                        completeness_basis=page.completeness_basis,
                        older_records_exist=older, warnings=tuple(warnings)),
                }

        page = self.client.search_with_evidence(
            postcode=postcode,
            postcode_prefix=postcode_prefix,
            from_date=from_date,
            to_date=to_date,
            min_price=min_price,
            max_price=max_price,
            property_type=property_type,
            estate_type=estate_type,
            transaction_category=transaction_category,
            new_build=new_build,
            limit=limit,
            offset=offset,
            order_desc=order_desc,
        )
        results = page.transactions

        return {
            "count": len(results),
            "limit": limit,
            "offset": offset,
            "results": results,
            "warnings": warnings,
            "raw": [t.raw for t in results] if include_raw else None,
            "provenance": live_provenance(
                evidence=page.evidence, sample_count=len(results),
                sample_limit=limit, warnings=tuple(warnings)),
        }

    def _probe_older_records(self, *, postcode: Optional[str],
                             postcode_prefix: Optional[str],
                             coverage_from: str) -> Optional[bool]:
        """One bounded probe. Any failure is None -- never False."""
        from property_core.ppd_probe import ExistenceProbe

        return ExistenceProbe().older_records_exist(
            postcode=postcode, postcode_prefix=postcode_prefix,
            coverage_from=coverage_from)

    def address_search(
        self,
        *,
        paon: Optional[str] = None,
        saon: Optional[str] = None,
        street: Optional[str] = None,
        town: Optional[str] = None,
        county: Optional[str] = None,
        locality: Optional[str] = None,
        district: Optional[str] = None,
        postcode: Optional[str] = None,
        postcode_prefix: Optional[str] = None,
        limit: int = 25,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Address-form search with strict limits. Always the live source.

        Returns a dict with keys: count, limit, offset, results, warnings, raw,
        provenance.
        """
        warnings: List[str] = []
        if limit <= 0:
            limit = 25
        if limit > FORM_MAX_LIMIT:
            warnings.append(f"limit capped to {FORM_MAX_LIMIT}")
            limit = FORM_MAX_LIMIT

        def _run_search(search_town: Optional[str]) -> list[PPDTransaction]:
            return self.client.sparql_search(
                paon=paon,
                saon=saon,
                street=street,
                town=search_town,
                county=county,
                locality=locality,
                district=district,
                postcode=postcode,
                postcode_prefix=postcode_prefix,
                limit=limit,
                order_desc=True,
            )

        results: list[PPDTransaction] = []
        try:
            results = _run_search(town)
        except Exception:  # noqa: BLE001
            if town:
                warnings.append("town filter failed; retrying without town")
                results = _run_search(None)
            else:
                raise

        if town and not results:
            warnings.append("town filter returned no results; retrying without town")
            results = _run_search(None)

        return {
            "count": len(results),
            "limit": limit,
            "offset": 0,
            "results": results,
            "warnings": warnings,
            "raw": [t.raw for t in results] if include_raw else None,
            # Always live (spec 2.6). This search takes no dates and means "this
            # property's history", which is routinely older than snapshot
            # coverage; bounding it would turn a real history into a partial one.
            "provenance": live_provenance(
                sample_count=len(results), sample_limit=limit,
                warnings=tuple(warnings)),
        }

    def comps(
        self,
        *,
        postcode: str,
        property_type: Optional[str] = None,
        transaction_category: Optional[str] = "A",
        filter_outliers: bool = False,
        months: int = 24,
        limit: int = DEFAULT_LIMIT,
        search_level: str = "sector",
        address: Optional[str] = None,
        auto_escalate: bool = True,
        thin_market_threshold: int = 5,
        coverage_policy: CoveragePolicy = CoveragePolicy.GUARANTEED,
    ) -> PPDCompsResponse:
        """Return comparable sales and summary stats for a postcode.

        Defaults are tuned for residential investment use cases:

        * ``transaction_category="A"`` — standard residential sales only.
          Pass ``None`` to include category-B (bulk transfers, non-standard
          conveyances) as well.
        * ``property_type=None`` — residential set (F/D/S/T). Pass a single
          code ("F"/"D"/"S"/"T"/"O") to filter to that one type, or the
          sentinel ``"ALL"`` to disable type filtering entirely (firehose).
        * ``filter_outliers=False`` — opt in to a 1.5*IQR price filter; when
          enabled, outlier transactions are dropped from BOTH the stats and
          the returned transaction list (needs >=4 prices, otherwise no-op).
        * ``auto_escalate=True`` — **compatibility parameter only.** Widening is
          disabled on the live source: the exhaustion evidence available here
          derives from the presentation limit, so geography would move with
          page size. The requested area is returned with a warning instead.

        If address is provided, also returns subject_property with its
        transaction history.

        All stats (median, mean, percentiles, min, max) are computed from the
        final filtered transaction list — after property-type filtering,
        subject-property removal, and optional outlier filtering — so they
        are always consistent with the returned ``transactions``.
        """
        if limit <= 0:
            limit = DEFAULT_LIMIT
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        # 1. Derive search prefix from postcode
        pc = postcode.upper().strip()
        if search_level == "postcode":
            prefix = None
            exact_postcode = pc
        elif search_level == "sector":
            parts = pc.split()
            if len(parts) == 2 and len(parts[1]) >= 1:
                prefix = f"{parts[0]} {parts[1][0]}"
            else:
                prefix = pc.split()[0] if pc else pc
            exact_postcode = None
        else:  # district
            prefix = pc.split()[0] if " " in pc else pc
            exact_postcode = None

        # 2. Resolve the property_type argument into a SPARQL filter value
        # and a post-fetch residential filter flag.
        #
        #   None       -> fetch all types, post-filter to F/D/S/T
        #   "ALL"      -> fetch all types, no post-filter (firehose)
        #   "F"/"D"/"S"/"T"/"O" -> push down to SPARQL, no post-filter
        if property_type is None:
            sparql_property_type: Optional[str] = None
            apply_residential_filter = True
        elif property_type == _PROPERTY_TYPE_ALL:
            sparql_property_type = None
            apply_residential_filter = False
        else:
            sparql_property_type = property_type
            apply_residential_filter = False

        # 3. Fetch transactions, from the snapshot when one is routable.
        #
        # Both bounds come from the shared contract. `months` means "ending
        # today", so the upper bound is today -- deriving only the lower one
        # left `requested_window` half-derived and half-literal, and a null
        # upper bound read as "unbounded request" when the request was in fact
        # bounded by today.
        from_date, to_date = window_from_months(months)
        warnings: list[str] = []

        transactions, provenance_for, from_snapshot = self._fetch_comps(
            exact_postcode=exact_postcode,
            prefix=prefix,
            from_date=from_date,
            to_date=to_date,
            sparql_property_type=sparql_property_type,
            apply_residential_filter=apply_residential_filter,
            transaction_category=transaction_category,
            limit=limit,
            coverage_policy=coverage_policy,
            warnings=warnings,
        )

        # 5. Subject property matching
        subject_property = None
        if address:
            try:
                subject_property = self._subject_property_lookup(
                    postcode, address, warnings=warnings)
            except InvalidPostcodeError:
                # Caller error. Must surface as 422, not be softened into a
                # warning that reads like an upstream hiccup.
                raise
            except Exception as exc:  # noqa: BLE001
                # A failed lookup is NOT an absent history. Comps still succeeds
                # (the resilience the old bare `except` provided), but the caller
                # is told the history was never checked.
                subject_property = None
                warnings.append(
                    "subject property lookup unavailable "
                    f"({type(exc).__name__}); sale history not checked"
                )
            if subject_property and subject_property.transaction_history:
                subject_ids = {t.transaction_id for t in subject_property.transaction_history}
                transactions = [t for t in transactions if t.transaction_id not in subject_ids]

        # 6. Drop priceless rows before stats / outlier filtering.
        transactions = [t for t in transactions if t.price is not None]

        # 7. Optional IQR outlier filter (1.5 * IQR rule, needs >= 4 prices).
        # Filter both the stats list and the returned transactions, so the
        # response remains internally consistent.
        if filter_outliers and len(transactions) >= 4:
            prices_for_iqr = [t.price for t in transactions]
            q = quantiles(prices_for_iqr, n=4)
            q1, q3 = q[0], q[2]
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            transactions = [t for t in transactions if lo <= t.price <= hi]

        prices = [t.price for t in transactions]
        count = len(transactions)

        # 8. Compute ALL stats from the final filtered list (fixes stats bug)
        computed_median = int(median(prices)) if prices else None
        computed_mean = int(round(mean(prices))) if prices else None
        p25 = None
        p75 = None
        if len(prices) >= 4:
            q = quantiles(prices, n=4)
            p25 = int(round(q[0]))
            p75 = int(round(q[2]))

        # 9. Subject comparison
        subject_price_percentile = None
        subject_vs_median_pct = None
        last_sale_price = (
            subject_property.last_sale.price
            if subject_property and subject_property.last_sale
            else None
        )
        if last_sale_price is not None and prices:
            below = sum(1 for p in prices if p < last_sale_price)
            subject_price_percentile = int((below / len(prices)) * 100)
            if isinstance(computed_median, int) and computed_median > 0:
                subject_vs_median_pct = round(
                    ((last_sale_price - computed_median) / computed_median) * 100, 1
                )

        query = PPDCompsQuery(
            postcode=postcode,
            property_type=property_type,
            months=months,
            search_level=search_level,
            address=address,
        )

        thin_market = count < thin_market_threshold

        # Auto-escalation stays DISABLED, on both sources.
        #
        # On the live path (PR 2) the only exhaustion evidence is
        # `raw_bindings_returned < fetch_limit`, and `fetch_limit` derives from
        # the caller's presentation limit -- so the evidence, and therefore the
        # geography, would move with page size. The snapshot adapter does supply
        # limit-independent evidence, which would make widening defensible, but
        # changing which area a caller's request covers is a behaviour change of
        # its own and is not in this PR's scope. Both paths return the requested
        # area and say why.
        if auto_escalate and thin_market:
            next_level = {"postcode": "sector", "sector": "district"}.get(search_level)
            if next_level:
                # Source-specific, because the reason differs. Saying
                # "live-source completeness" over a snapshot answer would be
                # false: the snapshot DOES establish completeness, and what
                # stops it widening is scope, not evidence.
                warnings.append(
                    f"auto-escalation not applied: the snapshot could establish "
                    f"safe escalation from {search_level} to {next_level}, but "
                    f"widening is not enabled; returning the requested area"
                    if from_snapshot else
                    "auto-escalation not applied: live-source completeness cannot "
                    f"establish safe escalation from {search_level} to "
                    f"{next_level}; returning the requested area")

        # Provenance is built ONCE, here, from evidence that is now complete --
        # the counts are final and every warning has been gathered. The block is
        # frozen, so a block built earlier and patched afterwards is not
        # available, and pydantic's validation-bypassing copy hatch is
        # prohibited for it.
        return PPDCompsResponse(
            query=query,
            provenance=provenance_for(count, tuple(warnings)),
            count=count,
            median=computed_median,
            mean=computed_mean,
            percentile_25=p25,
            percentile_75=p75,
            min=min(prices) if prices else None,
            max=max(prices) if prices else None,
            thin_market=thin_market,
            warnings=tuple(warnings),
            transactions=transactions,
            subject_property=subject_property,
            subject_price_percentile=subject_price_percentile,
            subject_vs_median_pct=subject_vs_median_pct,
        )

    def _fetch_comps(
        self,
        *,
        exact_postcode: Optional[str],
        prefix: Optional[str],
        from_date: str,
        #: The upper bound the caller asked for. Reported, not queried: the
        #: query needs no upper bound because nothing is dated in the future,
        #: but the window we SAY was requested must match the published meaning
        #: of `months` ("ending today").
        to_date: Optional[str],
        sparql_property_type: Optional[str],
        apply_residential_filter: bool,
        transaction_category: Optional[str],
        limit: int,
        coverage_policy: CoveragePolicy,
        warnings: List[str],
    ) -> tuple[List[PPDTransaction], Any, bool]:
        """Fetch comparables from the snapshot if routable, else live.

        Returns the rows, a callable that builds the provenance block once the
        final count and the complete warning list are known, and whether the
        snapshot answered -- the block is
        frozen and must be constructed atomically, so it cannot be built here
        and refined later. Patching one through pydantic's validation-bypassing
        copy hatch is prohibited for provenance.

        Appends to `warnings` in place: coverage narrowing, provisional-period
        and fallback notices all belong to the same list the response carries.
        """
        adapter = self._active_adapter()
        if adapter is not None:
            try:
                # Inside the try: a window the snapshot cannot reach raises
                # SnapshotCoverageGapError, and comps must still answer -- from
                # the live source, with a warning, like any snapshot failure.
                decision = resolve_coverage(
                    adapter, from_date=from_date, to_date=to_date,
                    policy=coverage_policy)
                page = adapter.search(
                    postcode=exact_postcode,
                    postcode_prefix=prefix,
                    from_date=decision.from_date,
                    # Type filtering is pushed into the query rather than applied
                    # afterwards. That is what makes limit+1 mean what it says:
                    # a short answer proves the SOURCE was exhausted, not merely
                    # that our own post-filter discarded most of a full page.
                    property_types=(
                        set(_RESIDENTIAL_TYPES) if apply_residential_filter
                        else ({sparql_property_type} if sparql_property_type else None)
                    ),
                    transaction_category=transaction_category,
                    limit=limit,
                    order_desc=True,
                )
            except SnapshotFailure as exc:
                warnings.append(fallback_warning(exc))
            else:
                warnings.extend(decision.warnings)

                def _provenance(count: int, gathered: tuple[str, ...]):
                    return snapshot_provenance(
                        adapter, decision=decision, sample_count=count,
                        sample_limit=limit,
                        completeness_basis=page.completeness_basis,
                        warnings=gathered)

                return list(page.transactions), _provenance, True

        live = self.client.search_with_evidence(
            postcode=exact_postcode,
            postcode_prefix=prefix,
            from_date=from_date,
            property_type=sparql_property_type,
            transaction_category=transaction_category,
            limit=limit,
            order_desc=True,
        )
        transactions = live.transactions

        # Containment and exhaustion are independent facts, reported separately.
        # An earlier version reported containment only inside the exhausted
        # branch while calling the page "saturated" -- a contradiction that meant
        # the message could never appear when it was true.
        if live.contained_out:
            warnings.append(
                f"{live.contained_out} out-of-area row(s) returned by the upstream "
                "were removed by geography containment"
            )
        if live.evidence.source_exhausted is not True:
            warnings.append(
                "result may be incomplete: the upstream window was not exhausted, "
                "so thin_market reflects the returned sample rather than the market"
            )

        # The live path cannot push the residential set down, so it filters here
        # -- which is exactly why its completeness evidence is untrustworthy.
        if apply_residential_filter:
            transactions = [t for t in transactions
                            if t.property_type in _RESIDENTIAL_TYPES]

        def _live_provenance(count: int, gathered: tuple[str, ...]):
            return live_provenance(
                evidence=live.evidence, sample_count=count, sample_limit=limit,
                warnings=gathered)

        return transactions, _live_provenance, False

    def _subject_property_lookup(
        self, postcode: str, address: str,
        warnings: Optional[List[str]] = None,
    ) -> Optional[SubjectProperty]:
        """Search for a specific property by postcode and address.

        Returns None rather than an ambiguous guess when:
          - the address lacks a parseable PAON (house number), or
          - the query returns transactions spanning multiple buildings, or
          - the SPARQL search fails for any reason.

        This is deliberate: a SubjectProperty represents one specific
        building. Callers that pass vague input (e.g. just a street name)
        get None, not the most-recent sale on the street labelled as "theirs".
        """
        paon = self._parse_paon(address)
        if paon is None:
            # No house number → can't identify a specific property
            return None

        # Use the part of the address after the PAON as the street filter
        address_clean = address.strip().split(",")[0].strip()
        words = address_clean.split()
        street = " ".join(words[1:]) if len(words) > 1 else None

        # Routed like every other read. This was hardwired live because an
        # eleven-year snapshot would truncate a property's history, and a
        # truncated history is indistinguishable from a complete one. Coverage
        # now runs from 1995, so the reason is gone -- and leaving it live left
        # the feature broken whenever the live source was.
        #
        # GUARANTEED, not EXPLICIT: this query names no dates, and the honest
        # answer to "the whole history" is the whole coverage plus a warning
        # saying so, not a refusal.
        provenance_for = None
        transactions = None

        adapter = self._active_adapter()
        if adapter is not None:
            try:
                decision = resolve_coverage(
                    adapter, from_date=None, to_date=None,
                    policy=CoveragePolicy.GUARANTEED)
                page = adapter.search(
                    postcode=postcode,
                    paon=paon,
                    street=street,
                    limit=50,
                    order_desc=True,
                )
            except SnapshotFailure as exc:
                # Falls back like any snapshot failure, and says so. Never
                # swallowed: a snapshot that cannot answer is not an absence.
                if warnings is not None:
                    warnings.append(fallback_warning(exc))
            else:
                transactions = list(page.transactions)

                def provenance_for(count: int):        # noqa: F811
                    return snapshot_provenance(
                        adapter, decision=decision, sample_count=count,
                        sample_limit=50,
                        completeness_basis=page.completeness_basis,
                        warnings=decision.warnings)

        if transactions is None:
            # Deliberately NOT wrapped in a bare except: an upstream failure must
            # reach comps() so it can be reported as "not checked" rather than
            # silently rendered as "no history".
            transactions = self.client.sparql_search(
                postcode=postcode,
                paon=paon,
                street=street,
                limit=50,
                order_desc=True,
            )

            def provenance_for(count: int):            # noqa: F811
                return live_provenance(sample_count=count, sample_limit=50)

        if not transactions:
            return None

        # Both sources match `paon` by SUBSTRING, so asking for "5" also returns
        # 15, 25 and 5A. Two separate problems follow, and the uniqueness check
        # alone solves neither:
        #
        #   * "5" was REFUSED because 15 came back with it -- though 5 is exactly
        #     one of the candidates and exactly what was asked for. Measured
        #     across six outcodes of the real artifact, this made 14% of
        #     addresses, 1 in 7, unresolvable.
        #   * "2" was ANSWERED WITH 25, because 25 was the only partial match
        #     and a single candidate passes a uniqueness check unchallenged.
        #     That is another property's sale history presented as yours, which
        #     is the failure this module exists to prevent.
        #
        # Narrowing to an exact `paon` first fixes both. It is not a relaxation:
        # nothing is selected that was not already returned, and the uniqueness
        # check still runs afterwards on what survives.
        wanted = self._normalise_paon(paon)
        exact = [t for t in transactions if self._normalise_paon(t.paon) == wanted]
        if not exact:
            # Every candidate merely CONTAINS the requested number. None of them
            # is the property that was asked for.
            return None
        transactions = exact

        # Uniqueness check: all matched transactions must represent the same
        # building. An exact house number is not identity on its own -- the same
        # number exists on other streets -- so this still has to hold.
        identities = {(t.paon, t.street) for t in transactions}
        if len(identities) != 1:
            return None

        # Sort by date desc — most recent sale first
        transactions.sort(key=lambda t: t.date or "", reverse=True)
        first = transactions[0]

        addr_parts: list[str] = []
        if first.paon:
            addr_parts.append(first.paon)
        if first.saon:
            addr_parts.append(first.saon)
        if first.street:
            addr_parts.append(first.street)
        if first.town:
            addr_parts.append(first.town)
        formatted_address = ", ".join(addr_parts) if addr_parts else address_clean

        return SubjectProperty(
            address=formatted_address,
            postcode=first.postcode or postcode,
            last_sale=first,
            transaction_count=len(transactions),
            transaction_history=transactions,
            # Still its own block even when both halves are snapshot-sourced.
            # The sample limits differ -- this asks for one property's whole
            # history at limit 50, comps asks a bounded window at its own limit
            # -- so one label over both would misstate one of them.
            provenance=provenance_for(len(transactions)),
        )

    @staticmethod
    def _normalise_paon(value: Optional[str]) -> str:
        """Compare house numbers on case and spacing only.

        Deliberately no more than that: "5" and "5A" are different properties,
        and anything that equated them would be inventing identity rather than
        comparing it.
        """
        return " ".join((value or "").upper().split())


    @staticmethod
    def _parse_paon(address: str) -> Optional[str]:
        """Extract a house number (PAON) from the start of an address.

        Returns None for addresses without a leading numeric token — i.e.
        bare street names, substrings, or building-name-only inputs. This
        is the parse-gate that prevents ambiguous queries.

        Examples:
            "39 Havenwood Rise"     -> "39"
            "42a High Street"       -> "42a"
            "Flat 4, 39 High St"    -> "39"  (falls through to second token)
            "Havenwood Rise"        -> None
            "Rose Cottage"          -> None
            "haven"                 -> None
        """
        parts = [p.strip() for p in address.strip().split(",")]
        # Walk through comma-separated parts looking for one starting with a digit.
        # This handles "Flat 4, 39 High Street" where the first part is the flat
        # and the second part has the PAON.
        for part in parts:
            if not part:
                continue
            words = part.split()
            if not words:
                continue
            first = words[0]
            # Accept: "39", "42a", "1b" — leading digit, short, alphanumeric
            if first[0].isdigit():
                return first
        return None

    def transaction_record(
        self,
        transaction_id: str,
        view: str = "all",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Fetch a single transaction record and normalize the result.

        Returns dict with keys: record (PPDTransactionRecord), raw (optional),
        provenance.

        **Always Linked Data, never the snapshot.** An exact id is a request for
        one specific transaction, which is frequently older than snapshot
        coverage; routing it to a bounded source would turn "here it is" into
        "not found" for every pre-coverage sale. This is also the remedy the
        coverage error points callers at, so it has to keep working.
        """
        record = self.client.get_transaction_record(transaction_id, view=view)
        return {
            "record": record,
            "raw": record.raw if include_raw else None,
            # One record, fetched by id: the sample is the record, and the
            # lookup is exhaustive by construction.
            "provenance": live_provenance(
                source=SourceKind.LINKED_DATA, sample_count=1, sample_limit=1),
        }


def _older_records_warnings(older: Optional[bool], coverage_from: Optional[str],
                            coverage_to: Optional[str]) -> tuple[str, ...]:
    """What an empty in-coverage result is allowed to say (spec 2.4).

    Asymmetric on purpose. `False` is the only value that licenses a bare empty
    result, because it is the only one backed by a probe that completed. `True`
    and `None` both warn, and neither response may read as "never sold".
    """
    if older is True:
        return (
            f"no sales within coverage {coverage_from}..{coverage_to}; earlier "
            f"records exist outside coverage",
        )
    if older is None:
        return (
            "coverage probe unavailable; cannot determine whether earlier "
            "records exist outside coverage",
        )
    return ()
