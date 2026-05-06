"""
Shared CSV / DataFrame utilities.
"""
import csv
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd

from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def load_csv(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    logger.info(f"Loaded {len(df)} rows from {path}")
    return df


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info(f"Saved {len(df)} rows → {path}")


def append_rows_to_csv(
    rows: List[dict],
    path: Path,
    fieldnames: Optional[List[str]] = None,
) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fieldnames is None:
        fieldnames = list(rows[0].keys())

    write_header = not path.exists() or path.stat().st_size == 0

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def dedupe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate leads.

    Strategy:
    - Rows WITH a valid place_id: dedupe only on place_id (it's authoritative).
    - Rows WITHOUT a place_id: dedupe on (name, address, phone) normalized.

    This ensures two Google Maps entries that share a name/address but have
    different place_ids are kept (they really are different records).
    """
    original_len = len(df)

    def norm(value) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    if "place_id" in df.columns:
        # Separate rows that have a real place_id from those that don't
        has_id = df["place_id"].str.strip().astype(bool)
        df_with = df[has_id].drop_duplicates(subset=["place_id"], keep="first")
        df_without = df[~has_id].copy()
    else:
        df_with = pd.DataFrame(columns=df.columns)
        df_without = df.copy()

    # Dedupe the no-place_id rows by name+address+phone
    if not df_without.empty:
        temp_cols = []
        for col in ("name", "address", "phone"):
            tmp = f"_norm_{col}"
            df_without[tmp] = df_without[col].apply(norm) if col in df_without.columns else ""
            temp_cols.append(tmp)
        df_without = df_without.drop_duplicates(subset=temp_cols, keep="first")
        df_without = df_without.drop(columns=temp_cols, errors="ignore")

    df = pd.concat([df_with, df_without], ignore_index=True)

    removed = original_len - len(df)
    if removed:
        logger.info(f"Dedupe: removed {removed} duplicates ({len(df)} remain)")

    return df.reset_index(drop=True)


def load_lines(path: Path) -> List[str]:
    """Load non-empty, non-comment lines from a plain text file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_checkpoint(path: Path) -> set:
    if not path.exists():
        return set()
    return set(path.read_text(encoding="utf-8").strip().splitlines())


def save_checkpoint(path: Path, completed: set) -> None:
    path.write_text("\n".join(sorted(completed)), encoding="utf-8")
