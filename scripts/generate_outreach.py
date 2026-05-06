#!/usr/bin/env python3
"""
AI-powered outreach generator.

Reads an enriched leads CSV and generates personalized cold emails, DMs,
SMS scripts, call scripts, and Loom video scripts for each lead.

Uses OpenAI (gpt-4o-mini by default) if OPENAI_API_KEY is set.
Falls back to built-in templates otherwise — no API key required for basic use.

Usage:
    # Template-only (no API key needed):
    python scripts/generate_outreach.py \\
        --input data/enriched/enriched_leads.csv \\
        --output data/outreach/outreach_ready.csv

    # AI-powered (requires OPENAI_API_KEY in .env):
    python scripts/generate_outreach.py \\
        --input data/enriched/enriched_leads.csv \\
        --output data/outreach/outreach_ready.csv \\
        --top 50 \\
        --model gpt-4o-mini

    # Resume: skip leads that already have outreach generated:
    python scripts/generate_outreach.py \\
        --input data/enriched/enriched_leads.csv \\
        --output data/outreach/outreach_ready.csv \\
        --skip-existing
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app import config
from app.outreach.generator import OutreachGenerator, default_crm_fields
from app.utils.csv_utils import load_csv, save_csv
from app.utils.logging_utils import get_logger
from app.utils.text_utils import clean_int, safe_str

logger = get_logger("generate_outreach")

OUTREACH_KEYS = [
    "cold_email_subject", "cold_email_body",
    "follow_up_1", "follow_up_2",
    "instagram_dm", "linkedin_dm",
    "sms_script", "call_script", "loom_video_script",
    "outreach_method",
]
CRM_KEYS = [
    "status", "priority", "last_contacted_at", "next_follow_up_at",
    "follow_up_count", "notes", "owner_response", "outreach_generated_at",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate AI outreach for leads")
    p.add_argument("--input", required=True,
                   help="Enriched leads CSV (output of enrich_leads.py)")
    p.add_argument("--output", default="data/outreach/outreach_ready.csv")
    p.add_argument("--top", type=int, default=0,
                   help="Process only the top N leads by lead_score (0 = all)")
    p.add_argument("--min-score", type=int, default=0,
                   help="Skip leads below this lead_score threshold")
    p.add_argument("--model", default=config.OPENAI_MODEL,
                   help=f"OpenAI model (default: {config.OPENAI_MODEL})")
    p.add_argument("--api-key", default=config.OPENAI_API_KEY,
                   help="OpenAI API key (defaults to OPENAI_API_KEY env var)")
    p.add_argument("--skip-existing", action="store_true",
                   help="Skip rows that already have a cold_email_subject in the output file")
    p.add_argument("--templates-only", action="store_true",
                   help="Force template-based generation (ignore API key)")
    p.add_argument("--delay", type=float, default=0.5,
                   help="Seconds between AI API calls (rate limiting)")
    return p.parse_args()


def load_existing_place_ids(output_path: Path) -> set[str]:
    """Return place_ids of rows that already have outreach generated."""
    if not output_path.exists():
        return set()
    try:
        existing = load_csv(output_path)
        if "cold_email_subject" not in existing.columns:
            return set()
        done = existing[
            existing["cold_email_subject"].str.strip() != ""
        ]["place_id"].tolist()
        return set(done)
    except Exception:
        return set()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    df = load_csv(input_path)

    # Sort by lead_score descending if column exists
    if "lead_score" in df.columns:
        df["_score_num"] = pd.to_numeric(df["lead_score"], errors="coerce").fillna(0)
        df = df.sort_values("_score_num", ascending=False).drop(columns=["_score_num"])

    # Filter by min score
    if args.min_score > 0 and "lead_score" in df.columns:
        before = len(df)
        df = df[pd.to_numeric(df["lead_score"], errors="coerce").fillna(0) >= args.min_score]
        logger.info(f"Min-score filter ({args.min_score}): {len(df)}/{before} rows kept")

    # Top N
    if args.top > 0:
        df = df.head(args.top)
        logger.info(f"Processing top {args.top} leads")

    # Skip existing
    existing_ids: set[str] = set()
    if args.skip_existing:
        existing_ids = load_existing_place_ids(output_path)
        logger.info(f"Skipping {len(existing_ids)} already-generated leads")

    # Build generator
    use_ai = not args.templates_only
    gen = OutreachGenerator(
        api_key=args.api_key,
        model=args.model,
        use_ai=use_ai,
        founder_name=config.FOUNDER_NAME,
    )

    results: list[dict] = []
    skipped = 0

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        place_id = safe_str(row.get("place_id", ""))
        name = safe_str(row.get("name", f"row {i}"))

        if place_id and place_id in existing_ids:
            skipped += 1
            continue

        logger.info(f"[{i}/{len(df)}] Generating: {name}")

        outreach = gen.generate(row)
        score = clean_int(row.get("lead_score", 0))
        crm = default_crm_fields(score)

        combined = {**row.to_dict(), **outreach, **crm}
        results.append(combined)

        # Rate limit between AI calls
        if outreach.get("outreach_method") == "ai" and i < len(df):
            time.sleep(args.delay)

    if skipped:
        logger.info(f"Skipped {skipped} already-processed leads")

    if not results:
        logger.info("No new leads to process.")
        return

    out_df = pd.DataFrame(results)

    # Merge with existing output if skip-existing was used
    if args.skip_existing and output_path.exists() and len(existing_ids) > 0:
        try:
            existing_df = load_csv(output_path)
            out_df = pd.concat([existing_df, out_df], ignore_index=True)
            # Re-sort by lead_score
            if "lead_score" in out_df.columns:
                out_df["_s"] = pd.to_numeric(out_df["lead_score"], errors="coerce").fillna(0)
                out_df = out_df.sort_values("_s", ascending=False).drop(columns=["_s"])
        except Exception as exc:
            logger.warning(f"Could not merge with existing output: {exc}")

    save_csv(out_df, output_path)
    logger.info(
        f"\nDone. Generated outreach for {len(results)} leads → {output_path}"
    )
    logger.info(
        "Next step: python scripts/prepare_email_campaign.py "
        f"--input {output_path} --output data/campaigns/email_campaign.csv"
    )


if __name__ == "__main__":
    main()
