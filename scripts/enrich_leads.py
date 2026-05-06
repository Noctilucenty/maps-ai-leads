#!/usr/bin/env python3
"""
Website enrichment + lead scoring.

Reads a raw leads CSV, scrapes each business website, scores every lead,
and outputs an enriched CSV ready for outreach generation.

Usage:
    python scripts/enrich_leads.py \\
        --input data/raw/batch_leads.csv \\
        --output data/enriched/enriched_leads.csv

    # Faster run (more workers, skip slow sites quickly):
    python scripts/enrich_leads.py \\
        --input data/raw/batch_leads.csv \\
        --output data/enriched/enriched_leads.csv \\
        --max-workers 8 \\
        --timeout 10
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.enrichers.website import enrich_dataframe
from app.scoring.lead_score import score_dataframe
from app.utils.csv_utils import dedupe_dataframe, load_csv, save_csv
from app.utils.logging_utils import get_logger

logger = get_logger("enrich_leads")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Website enrichment + lead scoring")
    p.add_argument("--input", required=True, help="Raw leads CSV from collect_leads or batch_collect")
    p.add_argument("--output", default="data/enriched/enriched_leads.csv")
    p.add_argument("--timeout", type=int, default=config.REQUEST_TIMEOUT,
                   help="HTTP timeout per website request (seconds)")
    p.add_argument("--max-pages", type=int, default=5,
                   help="Max pages to crawl per website")
    p.add_argument("--delay", type=float, default=0.4,
                   help="Delay between page fetches within a single site (seconds)")
    p.add_argument("--max-workers", type=int, default=5,
                   help="Parallel website workers")
    p.add_argument("--no-dedupe", action="store_true",
                   help="Skip deduplication step")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    df = load_csv(Path(args.input))
    logger.info(f"Loaded {len(df)} rows")

    if not args.no_dedupe:
        df = dedupe_dataframe(df)

    logger.info(f"Enriching {len(df)} websites (workers={args.max_workers})…")
    df = enrich_dataframe(
        df,
        timeout=args.timeout,
        max_pages=args.max_pages,
        delay=args.delay,
        max_workers=args.max_workers,
    )

    logger.info("Scoring leads…")
    df = score_dataframe(df)

    # Sort best leads first
    df = df.sort_values(
        by=["lead_score", "review_count", "rating"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)

    save_csv(df, Path(args.output))
    logger.info(
        f"Done. Top lead: "
        f"{df.iloc[0]['name'] if len(df) else 'n/a'} "
        f"(score: {df.iloc[0]['lead_score'] if len(df) else '—'})"
    )


if __name__ == "__main__":
    main()
