#!/usr/bin/env python3
"""
Single-query Google Maps lead collector.
For multi-city/multi-niche runs, use scripts/batch_collect.py instead.

Usage:
    python scripts/collect_leads.py \\
        --mode text \\
        --query "auto detailing shops in San Jose CA" \\
        --output data/raw/leads.csv

    python scripts/collect_leads.py \\
        --mode nearby \\
        --lat 37.3382 --lng -121.8863 \\
        --radius 8000 \\
        --keyword "window tint" \\
        --output data/raw/nearby_leads.csv
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.collectors.google_maps import GoogleMapsLeadCollector
from app.utils.csv_utils import save_csv
from app.utils.logging_utils import get_logger

import pandas as pd

logger = get_logger("collect_leads")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Google Maps lead collector (single query)"
    )
    p.add_argument("--api-key", default=config.GOOGLE_MAPS_API_KEY)
    p.add_argument("--mode", choices=["text", "nearby"], required=True)
    p.add_argument("--query", help="Text search query, e.g. 'auto repair in San Jose CA'")
    p.add_argument("--region", help="Optional ccTLD region, e.g. us")
    p.add_argument("--lat", type=float, help="Latitude (nearby mode)")
    p.add_argument("--lng", type=float, help="Longitude (nearby mode)")
    p.add_argument("--radius", type=int, default=5000, help="Radius in meters (nearby mode)")
    p.add_argument("--keyword", help="Keyword for nearby search, e.g. 'dentist'")
    p.add_argument("--business-type", help="Google business type, e.g. restaurant")
    p.add_argument("--max-pages", type=int, default=3, help="Max pagination pages (20 results/page)")
    p.add_argument("--no-details", action="store_true", help="Skip place details requests")
    p.add_argument("--output", default="data/raw/leads.csv")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.api_key:
        raise SystemExit(
            "No API key. Set GOOGLE_MAPS_API_KEY in .env or pass --api-key."
        )

    collector = GoogleMapsLeadCollector(
        api_key=args.api_key,
        delay_between_requests=config.RATE_LIMIT_SECONDS,
    )

    if args.mode == "text":
        if not args.query:
            raise SystemExit("--query is required in text mode.")
        logger.info(f"Text search: {args.query!r}")
        raw = collector.text_search(
            query=args.query,
            region=args.region,
            max_pages=args.max_pages,
        )
    else:
        if args.lat is None or args.lng is None:
            raise SystemExit("--lat and --lng are required in nearby mode.")
        logger.info(f"Nearby search at {args.lat},{args.lng} r={args.radius}m")
        raw = collector.nearby_search(
            location=(args.lat, args.lng),
            radius=args.radius,
            keyword=args.keyword,
            business_type=args.business_type,
            max_pages=args.max_pages,
        )

    logger.info(f"Found {len(raw)} raw results")

    rows = collector.enrich_places(raw, include_details=not args.no_details)
    df = pd.DataFrame(rows)
    save_csv(df, Path(args.output))


if __name__ == "__main__":
    main()
