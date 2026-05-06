#!/usr/bin/env python3
"""
Multi-city, multi-niche batch lead collector.

Reads a list of cities and niches, runs a Google Maps text search for every
combination, deduplicates results, and saves a single CSV.

Supports interrupted runs: a .checkpoint file tracks completed queries so
you can re-run after an API quota error without wasting calls.

Usage:
    python scripts/batch_collect.py \\
        --cities examples/cities.txt \\
        --niches examples/niches.txt \\
        --output data/raw/batch_leads.csv \\
        --state CA \\
        --max-results 60
"""
import argparse
import sys
import time
from pathlib import Path

# Allow importing from project root regardless of where the script is called from
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app import config
from app.collectors.google_maps import GoogleMapsLeadCollector
from app.utils.csv_utils import (
    append_rows_to_csv,
    dedupe_dataframe,
    load_checkpoint,
    load_csv,
    load_lines,
    save_checkpoint,
    save_csv,
)
from app.utils.logging_utils import get_logger

logger = get_logger("batch_collect")

# Canonical output field order (includes extra source columns)
FIELDNAMES = [
    "place_id", "name", "address", "phone", "international_phone",
    "website", "rating", "review_count", "business_status", "types",
    "latitude", "longitude", "google_maps_url",
    "source_query", "niche", "city",
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def build_queries(cities: list[str], niches: list[str], state: str) -> list[tuple]:
    """Return list of (query_str, niche, city) tuples."""
    queries = []
    for city in cities:
        for niche in niches:
            suffix = f" in {city}, {state}" if state else f" in {city}"
            query_str = f"{niche}{suffix}"
            queries.append((query_str, niche, city))
    return queries


def run_query(
    collector: GoogleMapsLeadCollector,
    query: str,
    niche: str,
    city: str,
    max_pages: int,
    include_details: bool,
) -> list[dict]:
    logger.info(f"  Searching: {query!r}")
    try:
        raw = collector.text_search(query=query, max_pages=max_pages)
    except RuntimeError as exc:
        logger.warning(f"  Search failed for {query!r}: {exc}")
        return []

    if not raw:
        logger.info("  → 0 results")
        return []

    rows = collector.enrich_places(
        raw,
        include_details=include_details,
        extra_fields={"source_query": query, "niche": niche, "city": city},
    )
    logger.info(f"  → {len(rows)} places enriched")
    return rows


def final_dedupe(output_path: Path) -> None:
    """Load the accumulated CSV, deduplicate, and save back."""
    if not output_path.exists() or output_path.stat().st_size == 0:
        return
    df = load_csv(output_path)
    df = dedupe_dataframe(df)
    save_csv(df, output_path)


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch Google Maps lead collector (multi-city × multi-niche)"
    )
    p.add_argument(
        "--cities", required=True,
        help="Path to text file with one city per line (e.g. examples/cities.txt)"
    )
    p.add_argument(
        "--niches", required=True,
        help="Path to text file with one niche per line (e.g. examples/niches.txt)"
    )
    p.add_argument(
        "--output", default="data/raw/batch_leads.csv",
        help="Output CSV path (default: data/raw/batch_leads.csv)"
    )
    p.add_argument(
        "--state", default="",
        help="State/region suffix to append to queries, e.g. CA"
    )
    p.add_argument(
        "--max-results", type=int, default=config.DEFAULT_MAX_RESULTS,
        help="Approximate max results per query (20 per page, max 3 pages = 60)"
    )
    p.add_argument(
        "--no-details", action="store_true",
        help="Skip individual place-details requests (faster, less data)"
    )
    p.add_argument(
        "--api-key", default=config.GOOGLE_MAPS_API_KEY,
        help="Google Maps API key (defaults to GOOGLE_MAPS_API_KEY env var)"
    )
    p.add_argument(
        "--delay", type=float, default=config.RATE_LIMIT_SECONDS,
        help=f"Seconds between API requests (default: {config.RATE_LIMIT_SECONDS})"
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.api_key:
        raise SystemExit(
            "No API key found. Set GOOGLE_MAPS_API_KEY in .env or pass --api-key."
        )

    cities = load_lines(Path(args.cities))
    niches = load_lines(Path(args.niches))
    logger.info(f"Loaded {len(cities)} cities × {len(niches)} niches "
                f"= {len(cities) * len(niches)} queries")

    queries = build_queries(cities, niches, args.state)
    output_path = Path(args.output)
    checkpoint_path = output_path.with_suffix(".checkpoint")

    completed = load_checkpoint(checkpoint_path)
    pending = [(q, n, c) for q, n, c in queries if q not in completed]
    skipped = len(queries) - len(pending)
    if skipped:
        logger.info(f"Resuming: {skipped} queries already done, {len(pending)} remaining")

    # Pages needed to get approx max_results (20 per page)
    max_pages = min(3, max(1, (args.max_results + 19) // 20))

    collector = GoogleMapsLeadCollector(
        api_key=args.api_key,
        delay_between_requests=args.delay,
    )

    total_saved = 0

    try:
        for i, (query, niche, city) in enumerate(pending, start=1):
            logger.info(f"[{i}/{len(pending)}] {query}")

            rows = run_query(
                collector=collector,
                query=query,
                niche=niche,
                city=city,
                max_pages=max_pages,
                include_details=not args.no_details,
            )

            if rows:
                append_rows_to_csv(rows, output_path, fieldnames=FIELDNAMES)
                total_saved += len(rows)

            completed.add(query)
            save_checkpoint(checkpoint_path, completed)

            time.sleep(args.delay)

    except KeyboardInterrupt:
        logger.info("\nInterrupted — partial results saved. Re-run to resume.")
    finally:
        logger.info(f"\nAppended ~{total_saved} rows to {output_path}")
        logger.info("Running final deduplication…")
        final_dedupe(output_path)

        if output_path.exists():
            df = load_csv(output_path)
            logger.info(f"Final result: {len(df)} unique leads in {output_path}")

        # Clean up checkpoint only if all queries completed
        if len(completed) == len(queries) and checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("All queries done — checkpoint file removed.")


if __name__ == "__main__":
    main()
