"""
Simple CSV-backed CRM status layer.
No database needed — works entirely with the outreach CSV.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from app.utils.csv_utils import load_csv, save_csv
from app.utils.logging_utils import get_logger
from app.utils.text_utils import normalize_text

logger = get_logger(__name__)

VALID_STATUSES = [
    "new",
    "enriched",
    "outreach_generated",
    "contacted",
    "follow_up_1_sent",
    "follow_up_2_sent",
    "replied",
    "interested",
    "demo_sent",
    "call_booked",
    "closed_won",
    "closed_lost",
    "not_interested",
]

CRM_COLUMNS = [
    "status",
    "priority",
    "last_contacted_at",
    "next_follow_up_at",
    "follow_up_count",
    "notes",
    "owner_response",
    "outreach_generated_at",
]


# ------------------------------------------------------------------
# Row finders
# ------------------------------------------------------------------

def find_rows(
    df: pd.DataFrame,
    business: Optional[str] = None,
    place_id: Optional[str] = None,
    index: Optional[int] = None,
) -> list[int]:
    """Return list of matching row indices (0-based)."""
    if index is not None:
        if 0 <= index < len(df):
            return [index]
        logger.warning(f"Index {index} out of range (0–{len(df) - 1})")
        return []

    if place_id:
        if "place_id" not in df.columns:
            logger.warning("No place_id column in file.")
            return []
        matches = df.index[df["place_id"] == place_id.strip()].tolist()
        if not matches:
            logger.warning(f"No row found with place_id={place_id!r}")
        return matches

    if business:
        if "name" not in df.columns:
            logger.warning("No name column in file.")
            return []
        needle = normalize_text(business)
        matches = df.index[
            df["name"].apply(normalize_text).str.contains(needle, na=False)
        ].tolist()
        if not matches:
            logger.warning(f"No row found matching name {business!r}")
        return matches

    logger.warning("Provide --business, --place-id, or --index to identify a row.")
    return []


# ------------------------------------------------------------------
# Status updater
# ------------------------------------------------------------------

def update_status(
    csv_path: Path,
    business: Optional[str] = None,
    place_id: Optional[str] = None,
    index: Optional[int] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    priority: Optional[str] = None,
    next_follow_up_at: Optional[str] = None,
    owner_response: Optional[str] = None,
) -> int:
    """
    Update CRM fields for matching rows. Returns the number of rows updated.
    Saves the file in-place.
    """
    if status and status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}. "
            f"Valid values: {', '.join(VALID_STATUSES)}"
        )

    df = load_csv(csv_path)

    # Ensure CRM columns exist
    for col in CRM_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    indices = find_rows(df, business=business, place_id=place_id, index=index)
    if not indices:
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for idx in indices:
        if status:
            df.at[idx, "status"] = status
            df.at[idx, "last_contacted_at"] = now

            # Auto-increment follow_up_count for follow-up statuses
            if "follow_up" in status:
                try:
                    count = int(df.at[idx, "follow_up_count"] or 0) + 1
                    df.at[idx, "follow_up_count"] = str(count)
                except (ValueError, TypeError):
                    df.at[idx, "follow_up_count"] = "1"

        if notes is not None:
            existing = str(df.at[idx, "notes"] or "").strip()
            appended = f"{now}: {notes}"
            df.at[idx, "notes"] = f"{existing}\n{appended}".strip()

        if priority is not None:
            df.at[idx, "priority"] = priority

        if next_follow_up_at is not None:
            df.at[idx, "next_follow_up_at"] = next_follow_up_at

        if owner_response is not None:
            df.at[idx, "owner_response"] = owner_response

        name = df.at[idx, "name"] if "name" in df.columns else f"row {idx}"
        logger.info(f"Updated [{idx}] {name!r} → status={status or '(unchanged)'}")

    save_csv(df, csv_path)
    return len(indices)


# ------------------------------------------------------------------
# Dashboard helpers
# ------------------------------------------------------------------

def get_pipeline_summary(df: pd.DataFrame) -> dict:
    """Return status counts for a quick pipeline overview."""
    if "status" not in df.columns:
        return {}
    counts = df["status"].value_counts().to_dict()
    return {s: counts.get(s, 0) for s in VALID_STATUSES if counts.get(s, 0) > 0}


def get_due_followups(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where next_follow_up_at is today or past."""
    if "next_follow_up_at" not in df.columns:
        return df.iloc[0:0]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mask = df["next_follow_up_at"].str[:10] <= today
    mask &= df["next_follow_up_at"].str.strip() != ""
    return df[mask].copy()
