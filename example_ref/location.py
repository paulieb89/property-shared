"""
Location intelligence system for UK postcode assessment.

Provides AI-powered location quality scoring with caching for efficiency.
Uses OpenAI Agents SDK for web research and synthesis.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import LocationAssessment, LocationBreakdown


# Default cache settings
DEFAULT_CACHE_DIR = Path("data")
DEFAULT_CACHE_TTL_DAYS = 30


class LocationCache:
    """
    SQLite-based cache for location assessments.

    Caches by outcode (e.g., "DE11") since location quality is similar
    within an outcode area. Full postcodes map to their outcode cache.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
    ):
        """
        Initialize location cache.

        Args:
            db_path: Path to SQLite database. Defaults to data/location_cache.db
            ttl_days: Cache time-to-live in days
        """
        if db_path is None:
            DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            db_path = DEFAULT_CACHE_DIR / "location_cache.db"

        self.db_path = Path(db_path)
        self.ttl_days = ttl_days
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS location_assessments (
                    outcode TEXT PRIMARY KEY,
                    score INTEGER NOT NULL,
                    breakdown_json TEXT NOT NULL,
                    reasoning TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    data_sources_json TEXT NOT NULL,
                    assessed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at
                ON location_assessments(expires_at)
            """)
            conn.commit()

    @staticmethod
    def extract_outcode(postcode: str) -> str:
        """Extract outcode from a full or partial postcode."""
        parts = postcode.strip().upper().split()
        return parts[0] if parts else postcode.upper()

    def get(self, postcode: str) -> LocationAssessment | None:
        """
        Get cached assessment for a postcode.

        Args:
            postcode: Full or partial UK postcode

        Returns:
            LocationAssessment if cached and valid, None otherwise
        """
        outcode = self.extract_outcode(postcode)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM location_assessments WHERE outcode = ?",
                (outcode,)
            ).fetchone()

            if not row:
                return None

            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now() > expires_at:
                # Cache expired, delete and return None
                conn.execute(
                    "DELETE FROM location_assessments WHERE outcode = ?",
                    (outcode,)
                )
                conn.commit()
                return None

            breakdown = LocationBreakdown(**json.loads(row["breakdown_json"]))

            return LocationAssessment(
                postcode=postcode,  # Return with original postcode
                score=row["score"],
                breakdown=breakdown,
                reasoning=row["reasoning"],
                confidence=row["confidence"],
                data_sources=json.loads(row["data_sources_json"]),
                cached=True,
                assessed_at=datetime.fromisoformat(row["assessed_at"]),
                cache_expires_at=expires_at,
            )

    def set(self, assessment: LocationAssessment) -> None:
        """
        Store an assessment in the cache.

        Args:
            assessment: LocationAssessment to cache
        """
        outcode = self.extract_outcode(assessment.postcode)
        expires_at = datetime.now() + timedelta(days=self.ttl_days)

        breakdown_json = json.dumps({
            "safety": assessment.breakdown.safety,
            "schools": assessment.breakdown.schools,
            "transport": assessment.breakdown.transport,
            "amenities": assessment.breakdown.amenities,
            "employment": assessment.breakdown.employment,
            "rental_demand": assessment.breakdown.rental_demand,
        })

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO location_assessments
                (outcode, score, breakdown_json, reasoning, confidence,
                 data_sources_json, assessed_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                outcode,
                assessment.score,
                breakdown_json,
                assessment.reasoning,
                assessment.confidence,
                json.dumps(assessment.data_sources),
                assessment.assessed_at.isoformat(),
                expires_at.isoformat(),
            ))
            conn.commit()

    def invalidate(self, postcode: str) -> bool:
        """
        Remove a cached assessment.

        Args:
            postcode: Full or partial UK postcode

        Returns:
            True if an entry was removed, False otherwise
        """
        outcode = self.extract_outcode(postcode)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM location_assessments WHERE outcode = ?",
                (outcode,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM location_assessments WHERE expires_at < ?",
                (datetime.now().isoformat(),)
            )
            conn.commit()
            return cursor.rowcount

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM location_assessments"
            ).fetchone()[0]

            valid = conn.execute(
                "SELECT COUNT(*) FROM location_assessments WHERE expires_at > ?",
                (datetime.now().isoformat(),)
            ).fetchone()[0]

            return {
                "total_entries": total,
                "valid_entries": valid,
                "expired_entries": total - valid,
                "ttl_days": self.ttl_days,
                "db_path": str(self.db_path),
            }


class LocationManager:
    """
    Orchestrates location assessment with caching and AI research.

    Flow:
    1. Check cache for existing assessment
    2. If cache miss, run location research agent
    3. Cache the result
    4. Return assessment
    """

    def __init__(
        self,
        cache: LocationCache | None = None,
        use_cache: bool = True,
    ):
        """
        Initialize location manager.

        Args:
            cache: LocationCache instance (creates default if None)
            use_cache: Whether to use caching (default True)
        """
        self.cache = cache or LocationCache()
        self.use_cache = use_cache

    def assess(self, postcode: str, address: str | None = None) -> LocationAssessment:
        """
        Get location assessment for a UK postcode.

        Checks cache first, then runs AI research if needed.

        Args:
            postcode: Full UK postcode (e.g., "DE11 9AB")
            address: Optional full address for more specific context

        Returns:
            LocationAssessment with score and breakdown
        """
        # Check cache first
        if self.use_cache:
            cached = self.cache.get(postcode)
            if cached:
                return cached

        # Run AI assessment
        assessment = self._run_assessment(postcode, address)

        # Cache the result
        if self.use_cache:
            self.cache.set(assessment)

        return assessment

    async def assess_async(self, postcode: str, address: str | None = None) -> LocationAssessment:
        """
        Async version of assess().

        Args:
            postcode: Full UK postcode
            address: Optional full address for more specific context

        Returns:
            LocationAssessment with score and breakdown
        """
        # Check cache first
        if self.use_cache:
            cached = self.cache.get(postcode)
            if cached:
                return cached

        # Run AI assessment asynchronously
        assessment = await self._run_assessment_async(postcode, address)

        # Cache the result
        if self.use_cache:
            self.cache.set(assessment)

        return assessment

    def batch_assess(self, postcodes: list[str]) -> dict[str, LocationAssessment]:
        """
        Assess multiple postcodes efficiently.

        Groups by outcode to avoid redundant assessments.

        Args:
            postcodes: List of UK postcodes

        Returns:
            Dict mapping postcode to LocationAssessment
        """
        results: dict[str, LocationAssessment] = {}
        outcodes_to_assess: set[str] = set()

        # First pass: check cache and group by outcode
        for postcode in postcodes:
            if self.use_cache:
                cached = self.cache.get(postcode)
                if cached:
                    results[postcode] = cached
                    continue

            outcode = LocationCache.extract_outcode(postcode)
            outcodes_to_assess.add(outcode)

        # Second pass: assess missing outcodes
        for outcode in outcodes_to_assess:
            assessment = self._run_assessment(outcode)
            if self.use_cache:
                self.cache.set(assessment)

            # Map all postcodes with this outcode to this assessment
            for postcode in postcodes:
                if postcode not in results:
                    if LocationCache.extract_outcode(postcode) == outcode:
                        # Create a copy with the specific postcode
                        results[postcode] = LocationAssessment(
                            postcode=postcode,
                            score=assessment.score,
                            breakdown=assessment.breakdown,
                            reasoning=assessment.reasoning,
                            confidence=assessment.confidence,
                            data_sources=assessment.data_sources,
                            cached=assessment.cached,
                            assessed_at=assessment.assessed_at,
                            cache_expires_at=assessment.cache_expires_at,
                        )

        return results

    def _run_assessment(self, postcode: str, address: str | None = None) -> LocationAssessment:
        """
        Run synchronous AI assessment for a postcode.

        This is a wrapper that runs the async version synchronously.
        For production use, prefer assess_async() directly.

        Args:
            postcode: UK postcode to assess
            address: Optional full address for more specific context

        Returns:
            LocationAssessment from AI research
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an async context, create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._run_assessment_async(postcode, address)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._run_assessment_async(postcode, address))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self._run_assessment_async(postcode, address))

    async def _run_assessment_async(self, postcode: str, address: str | None = None) -> LocationAssessment:
        """
        Run AI-powered location assessment with parallel searches.

        Runs 6 factor searches in parallel using asyncio.gather() for ~5x speedup.

        Args:
            postcode: UK postcode to assess
            address: Optional full address for more specific context

        Returns:
            LocationAssessment from AI research
        """
        import asyncio
        from agents import Agent, Runner, WebSearchTool, ModelSettings
        from openai.types.shared import Reasoning

        outcode = LocationCache.extract_outcode(postcode)
        address_context = f" near {address}" if address else ""

        # Define search queries for each factor
        factor_queries = {
            "safety": f"crime rates antisocial behavior statistics {outcode} UK police data",
            "schools": f"Ofsted school ratings {outcode} UK primary secondary outstanding good",
            "transport": f"public transport train bus stations {outcode} UK commute links motorway",
            "amenities": f"shops restaurants pubs supermarkets healthcare GP {outcode} UK",
            "employment": f"job market major employers business parks {outcode} UK employment",
            "rental_demand": f"rental market tenant demand lettings agents {outcode} UK BTL",
        }

        async def search_factor(factor: str, query: str) -> tuple[str, str]:
            """Run a single factor search and return (factor, summary)."""
            # Create agent inline with GPT-5 Responses API settings for speed
            # Use effort="none" for lowest latency (web_search incompatible with "minimal" only)
            agent = Agent(
                name=f"{factor.title()} Researcher",
                model="gpt-5-mini",
                model_settings=ModelSettings(
                    reasoning=Reasoning(effort="low"),
                    verbosity="low",
                ),
                instructions=f"""You are a UK location researcher focused on {factor}.
Search for the query and return a 2-3 sentence summary with specific facts,
statistics, or ratings you find. Be concise and factual.""",
                tools=[WebSearchTool(user_location={"type": "approximate", "country": "GB"})],
            )
            try:
                result = await Runner.run(agent, f"{query}{address_context}")
                return (factor, str(result.final_output))
            except Exception as e:
                return (factor, f"Search failed: {e}")

        try:
            # Run all 6 searches in parallel
            tasks = [search_factor(f, q) for f, q in factor_queries.items()]
            results = await asyncio.gather(*tasks)
            search_results = dict(results)

            # Synthesize results into final assessment
            return await self._synthesize_assessment(search_results, postcode, address)

        except Exception as e:
            # Fallback to neutral assessment on error
            return LocationAssessment(
                postcode=postcode,
                score=50,
                breakdown=LocationBreakdown(),
                reasoning=f"Unable to assess location: {str(e)}",
                confidence=0.0,
                data_sources=["fallback"],
            )

    async def _synthesize_assessment(
        self,
        search_results: dict[str, str],
        postcode: str,
        address: str | None
    ) -> LocationAssessment:
        """
        Synthesize parallel search results into a LocationAssessment.

        Args:
            search_results: Dict mapping factor name to search summary
            postcode: Original postcode
            address: Optional address for context

        Returns:
            LocationAssessment with scores derived from search results
        """
        from agents import Agent, Runner, ModelSettings
        from openai.types.shared import Reasoning

        outcode = LocationCache.extract_outcode(postcode)

        # Format search results for scoring
        results_text = "\n\n".join([
            f"**{factor.upper()}**:\n{summary}"
            for factor, summary in search_results.items()
        ])

        scoring_prompt = f"""Based on these research findings for UK postcode {outcode}, provide location scores.

{results_text}

Analyze the findings and provide your assessment as a JSON object:
{{
    "score": <overall 0-100>,
    "breakdown": {{
        "safety": <0-100>,
        "schools": <0-100>,
        "transport": <0-100>,
        "amenities": <0-100>,
        "employment": <0-100>,
        "rental_demand": <0-100>
    }},
    "reasoning": "<2-3 sentence summary of key location characteristics>",
    "local_highlights": [
        "<specific named feature from the research>",
        "<another specific feature>"
    ],
    "confidence": <0.0-1.0 based on data quality>,
    "data_sources": ["web_search"]
}}

Score guidelines:
- 80-100: Excellent (outstanding schools, very low crime, excellent transport)
- 60-79: Good (good schools, below average crime, decent amenities)
- 40-59: Average (mixed results, typical for the region)
- 20-39: Below average (some concerns, limited amenities)
- 0-19: Poor (high crime, failing schools, poor transport)

Return ONLY the JSON object, no other text."""

        try:
            scoring_agent = Agent(
                name="Location Scorer",
                model="gpt-5-mini",
                model_settings=ModelSettings(
                    reasoning=Reasoning(effort="low"),
                    verbosity="low",
                ),
                instructions="You convert location research into numerical scores. Return only valid JSON.",
            )
            result = await Runner.run(scoring_agent, scoring_prompt)
            response_text = str(result.final_output)
            return self._parse_assessment_response(response_text, postcode)

        except Exception as e:
            # Fallback with neutral scores
            return LocationAssessment(
                postcode=postcode,
                score=50,
                breakdown=LocationBreakdown(),
                reasoning=f"Scoring failed: {str(e)}. Search data was collected.",
                confidence=0.3,
                data_sources=["web_search", "scoring_fallback"],
            )

    def _parse_assessment_response(
        self,
        response: str,
        postcode: str
    ) -> LocationAssessment:
        """
        Parse AI response into LocationAssessment.

        Args:
            response: Raw response from location agent
            postcode: Original postcode being assessed

        Returns:
            Parsed LocationAssessment
        """
        import re

        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            # No JSON found, create neutral assessment
            return LocationAssessment(
                postcode=postcode,
                score=50,
                breakdown=LocationBreakdown(),
                reasoning=response[:500] if response else "No assessment available",
                confidence=0.3,
                data_sources=["llm_inference"],
            )

        try:
            data = json.loads(json_match.group())

            breakdown_data = data.get("breakdown", {})
            breakdown = LocationBreakdown(
                safety=int(breakdown_data.get("safety", 50)),
                schools=int(breakdown_data.get("schools", 50)),
                transport=int(breakdown_data.get("transport", 50)),
                amenities=int(breakdown_data.get("amenities", 50)),
                employment=int(breakdown_data.get("employment", 50)),
                rental_demand=int(breakdown_data.get("rental_demand", 50)),
            )

            # Extract local highlights (list of strings)
            local_highlights = data.get("local_highlights", [])
            if not isinstance(local_highlights, list):
                local_highlights = []
            # Ensure all items are strings and limit to 5
            local_highlights = [str(h) for h in local_highlights[:5] if h]

            return LocationAssessment(
                postcode=postcode,
                score=int(data.get("score", breakdown.average)),
                breakdown=breakdown,
                reasoning=str(data.get("reasoning", ""))[:1000],
                confidence=float(data.get("confidence", 0.7)),
                data_sources=data.get("data_sources", ["web_search"]),
                local_highlights=local_highlights,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # JSON parse failed, create neutral assessment
            return LocationAssessment(
                postcode=postcode,
                score=50,
                breakdown=LocationBreakdown(),
                reasoning="Could not parse location assessment",
                confidence=0.2,
                data_sources=["parse_error"],
                local_highlights=[],
            )
