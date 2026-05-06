"""Tests for deduplication logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from app.utils.csv_utils import dedupe_dataframe


def test_dedupe_by_place_id():
    df = pd.DataFrame([
        {"place_id": "A", "name": "Shop A", "address": "123 Main St", "phone": "555-1234"},
        {"place_id": "A", "name": "Shop A", "address": "123 Main St", "phone": "555-1234"},
        {"place_id": "B", "name": "Shop B", "address": "456 Oak Ave", "phone": "555-5678"},
    ])
    result = dedupe_dataframe(df)
    assert len(result) == 2
    assert set(result["place_id"]) == {"A", "B"}


def test_dedupe_by_name_address_phone():
    df = pd.DataFrame([
        {"name": "Shop A", "address": "123 Main St", "phone": "555-1234"},
        {"name": "Shop A", "address": "123 Main St", "phone": "555-1234"},
        {"name": "Shop B", "address": "456 Oak Ave", "phone": "555-5678"},
    ])
    result = dedupe_dataframe(df)
    assert len(result) == 2


def test_dedupe_case_insensitive():
    df = pd.DataFrame([
        {"place_id": "", "name": "SHOP A", "address": "123 Main St", "phone": "555-1234"},
        {"place_id": "", "name": "shop a", "address": "123 main st", "phone": "555-1234"},
    ])
    result = dedupe_dataframe(df)
    assert len(result) == 1


def test_dedupe_normalizes_whitespace():
    df = pd.DataFrame([
        {"place_id": "", "name": "  Shop A  ", "address": "123  Main St", "phone": "555-1234"},
        {"place_id": "", "name": "Shop A", "address": "123 Main St", "phone": "555-1234"},
    ])
    result = dedupe_dataframe(df)
    assert len(result) == 1


def test_dedupe_prefers_place_id_over_name_address():
    # Same name+address but different place_ids → keep both
    df = pd.DataFrame([
        {"place_id": "A", "name": "Shop A", "address": "123 Main St", "phone": ""},
        {"place_id": "B", "name": "Shop A", "address": "123 Main St", "phone": ""},
    ])
    result = dedupe_dataframe(df)
    assert len(result) == 2


def test_empty_dataframe():
    df = pd.DataFrame(columns=["place_id", "name", "address", "phone"])
    result = dedupe_dataframe(df)
    assert len(result) == 0


def test_single_row_unchanged():
    df = pd.DataFrame([
        {"place_id": "A", "name": "Shop A", "address": "123 Main", "phone": "555-0000"}
    ])
    result = dedupe_dataframe(df)
    assert len(result) == 1


def test_no_place_id_column_falls_back_to_name():
    df = pd.DataFrame([
        {"name": "Shop A", "address": "123 Main St", "phone": "555-1234"},
        {"name": "Shop A", "address": "123 Main St", "phone": "555-1234"},
        {"name": "Shop B", "address": "456 Oak Ave", "phone": "555-5678"},
    ])
    result = dedupe_dataframe(df)
    assert len(result) == 2
