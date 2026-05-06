#!/usr/bin/env python3
"""
CRM status updater — update lead status, notes, priority, and follow-up dates.

Identify a lead by:
  --business "ABC Auto Detail"   (fuzzy name match)
  --place-id "ChIJ..."           (exact place_id match)
  --index 5                      (row number, 0-based)

Usage:
    python scripts/update_status.py \\
        --file data/outreach/outreach_ready.csv \\
        --business "Dragon Auto Works" \\
        --status contacted \\
        --notes "Sent cold email #1 via Gmail"

    python scripts/update_status.py \\
        --file data/outreach/outreach_ready.csv \\
        --place-id "ChIJNY1h0VnLj4AR-FrFUrDWZz0" \\
        --status replied \\
        --owner-response "Interested, wants a demo call"

    python scripts/update_status.py \\
        --file data/outreach/outreach_ready.csv \\
        --index 3 \\
        --status call_booked \\
        --next-follow-up "2026-05-15" \\
        --priority high

    # View pipeline summary:
    python scripts/update_status.py \\
        --file data/outreach/outreach_ready.csv \\
        --summary
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crm.status import (
    VALID_STATUSES,
    get_pipeline_summary,
    update_status,
)
from app.utils.csv_utils import load_csv
from app.utils.logging_utils import get_logger

logger = get_logger("update_status")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Update CRM status for a lead")
    p.add_argument("--file", required=True, help="Path to outreach_ready.csv")

    # Identifier (one required unless --summary)
    id_group = p.add_mutually_exclusive_group()
    id_group.add_argument("--business", help="Fuzzy match on business name")
    id_group.add_argument("--place-id", dest="place_id", help="Exact place_id")
    id_group.add_argument("--index", type=int, help="Row index (0-based)")

    # Fields to update
    p.add_argument(
        "--status", choices=VALID_STATUSES,
        help="New CRM status"
    )
    p.add_argument("--notes", help="Append a note (timestamped automatically)")
    p.add_argument("--priority", choices=["high", "medium", "low", "skip"],
                   help="Update priority")
    p.add_argument("--next-follow-up", dest="next_follow_up",
                   help="Next follow-up date (YYYY-MM-DD)")
    p.add_argument("--owner-response", dest="owner_response",
                   help="Record owner/prospect response")

    p.add_argument("--summary", action="store_true",
                   help="Print pipeline summary and exit")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.file)

    if not csv_path.exists():
        raise SystemExit(f"File not found: {csv_path}")

    if args.summary:
        df = load_csv(csv_path)
        summary = get_pipeline_summary(df)
        print(f"\nPipeline summary — {csv_path.name}\n{'─' * 40}")
        for status, count in summary.items():
            bar = "█" * min(count, 40)
            print(f"  {status:<25} {count:>4}  {bar}")
        print(f"\n  Total: {len(df)} leads\n")
        return

    if not any([args.business, args.place_id, args.index is not None]):
        raise SystemExit(
            "Provide one of --business, --place-id, or --index to identify a row.\n"
            "Or use --summary to view pipeline status."
        )

    if not any([args.status, args.notes, args.priority,
                args.next_follow_up, args.owner_response]):
        raise SystemExit(
            "Nothing to update. Provide at least one of: "
            "--status, --notes, --priority, --next-follow-up, --owner-response"
        )

    updated = update_status(
        csv_path=csv_path,
        business=args.business,
        place_id=args.place_id,
        index=args.index,
        status=args.status,
        notes=args.notes,
        priority=args.priority,
        next_follow_up_at=args.next_follow_up,
        owner_response=args.owner_response,
    )

    if updated:
        print(f"Updated {updated} row(s) in {csv_path}")
    else:
        print("No rows updated. Check your identifier.")


if __name__ == "__main__":
    main()
