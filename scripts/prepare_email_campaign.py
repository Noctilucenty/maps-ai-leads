#!/usr/bin/env python3
"""
Prepare a mail-merge CSV ready to import into Instantly, Smartlead,
Lemlist, GMass, Mailmeteor, or any cold email tool.

Only includes leads that have:
  - an email address found
  - a generated cold_email_subject and cold_email_body

Usage:
    python scripts/prepare_email_campaign.py \\
        --input data/outreach/outreach_ready.csv \\
        --output data/campaigns/email_campaign.csv

    # Filter to high-priority leads above score 70:
    python scripts/prepare_email_campaign.py \\
        --input data/outreach/outreach_ready.csv \\
        --output data/campaigns/email_campaign.csv \\
        --min-score 70 \\
        --priority high

    # Limit to 100 rows:
    python scripts/prepare_email_campaign.py \\
        --input data/outreach/outreach_ready.csv \\
        --output data/campaigns/email_campaign.csv \\
        --limit 100
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.utils.csv_utils import load_csv, save_csv
from app.utils.logging_utils import get_logger
from app.utils.text_utils import safe_str

logger = get_logger("prepare_email_campaign")

CAMPAIGN_COLUMNS = [
    "recipient_email",
    "business_name",
    "city",
    "niche",
    "subject",
    "body",
    "follow_up_1",
    "follow_up_2",
    "status",
    "priority",
    "lead_score",
    "website",
    "phone",
    "instagram",
    "facebook",
    "pain_points",
    "pitch_angle",
    "recommended_offer",
    "google_maps_url",
    "place_id",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prepare mail-merge CSV from outreach-ready leads"
    )
    p.add_argument("--input", required=True,
                   help="outreach_ready.csv from generate_outreach.py")
    p.add_argument("--output", default="data/campaigns/email_campaign.csv")
    p.add_argument("--min-score", type=int, default=0,
                   help="Minimum lead_score to include")
    p.add_argument("--priority", choices=["high", "medium", "low"],
                   help="Filter by priority level")
    p.add_argument("--status",
                   help="Filter by CRM status (e.g. outreach_generated)")
    p.add_argument("--limit", type=int, default=0,
                   help="Maximum number of email rows to output (0 = no limit)")
    p.add_argument("--one-email-per-lead", action="store_true",
                   help="If a lead has multiple emails, use only the first one")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    df = load_csv(Path(args.input))
    original_len = len(df)
    logger.info(f"Loaded {original_len} rows")

    # --- Filters ---
    if args.status:
        df = df[df.get("status", pd.Series(dtype=str)) == args.status]
        logger.info(f"Status filter '{args.status}': {len(df)} rows remain")

    if args.priority and "priority" in df.columns:
        df = df[df["priority"] == args.priority]
        logger.info(f"Priority filter '{args.priority}': {len(df)} rows remain")

    if args.min_score > 0 and "lead_score" in df.columns:
        df = df[pd.to_numeric(df["lead_score"], errors="coerce").fillna(0) >= args.min_score]
        logger.info(f"Min-score filter ({args.min_score}): {len(df)} rows remain")

    # --- Drop rows without email or outreach ---
    df = df[df.get("emails", pd.Series(dtype=str)).str.strip() != ""]
    df = df[df.get("cold_email_subject", pd.Series(dtype=str)).str.strip() != ""]
    logger.info(f"Has email + outreach: {len(df)} rows remain")

    if df.empty:
        logger.warning(
            "No rows with email addresses AND generated outreach. "
            "Run enrich_leads.py first, then generate_outreach.py."
        )
        return

    # --- Build campaign rows (one per email address) ---
    campaign_rows: list[dict] = []

    for _, row in df.iterrows():
        raw_emails = safe_str(row.get("emails", ""))
        email_list = [e.strip() for e in raw_emails.split(";") if e.strip()]

        if not email_list:
            continue

        if args.one_email_per_lead:
            email_list = [email_list[0]]

        for email in email_list:
            campaign_rows.append({
                "recipient_email": email,
                "business_name": safe_str(row.get("name", "")),
                "city": safe_str(row.get("city", "")),
                "niche": safe_str(row.get("niche", "")),
                "subject": safe_str(row.get("cold_email_subject", "")),
                "body": safe_str(row.get("cold_email_body", "")),
                "follow_up_1": safe_str(row.get("follow_up_1", "")),
                "follow_up_2": safe_str(row.get("follow_up_2", "")),
                "status": safe_str(row.get("status", "")),
                "priority": safe_str(row.get("priority", "")),
                "lead_score": safe_str(row.get("lead_score", "")),
                "website": safe_str(row.get("website", "")),
                "phone": safe_str(row.get("phone", "")),
                "instagram": safe_str(row.get("instagram", "")),
                "facebook": safe_str(row.get("facebook", "")),
                "pain_points": safe_str(row.get("pain_points", "")),
                "pitch_angle": safe_str(row.get("pitch_angle", "")),
                "recommended_offer": safe_str(row.get("recommended_offer", "")),
                "google_maps_url": safe_str(row.get("google_maps_url", "")),
                "place_id": safe_str(row.get("place_id", "")),
            })

    out_df = pd.DataFrame(campaign_rows, columns=CAMPAIGN_COLUMNS)

    if args.limit > 0:
        out_df = out_df.head(args.limit)
        logger.info(f"Limit applied: {len(out_df)} rows")

    save_csv(out_df, Path(args.output))

    logger.info(
        f"\nCampaign ready: {len(out_df)} email rows → {args.output}\n"
        "Import into: Instantly / Smartlead / Lemlist / GMass / Mailmeteor\n"
        "Column mapping:\n"
        "  recipient_email → To\n"
        "  subject         → Subject\n"
        "  body            → Email body (sequence step 1)\n"
        "  follow_up_1     → Sequence step 2\n"
        "  follow_up_2     → Sequence step 3\n"
    )


if __name__ == "__main__":
    main()
