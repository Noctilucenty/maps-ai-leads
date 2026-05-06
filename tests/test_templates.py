"""Tests for template-based outreach generation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from app.outreach.generator import OutreachGenerator
from app.outreach.templates import generate_from_templates

REQUIRED_KEYS = [
    "cold_email_subject",
    "cold_email_body",
    "follow_up_1",
    "follow_up_2",
    "instagram_dm",
    "linkedin_dm",
    "sms_script",
    "call_script",
    "loom_video_script",
]


def make_row(**kwargs) -> pd.Series:
    defaults = {
        "name": "Dragon Auto Works",
        "niche": "auto repair",
        "city": "San Jose",
        "rating": "4.6",
        "review_count": "85",
        "website": "https://example.com",
        "emails": "",
        "has_contact_form": "False",
        "has_booking": "False",
        "instagram": "",
        "facebook": "",
        "lead_score": "78",
        "pain_points": "No email contact visible;No online booking system",
        "pitch_angle": "Phone-only contact: pitch missed-call SMS recovery + AI booking",
        "recommended_offer": "AI Receptionist + Missed-Call SMS Recovery",
    }
    defaults.update(kwargs)
    return pd.Series(defaults)


# ------------------------------------------------------------------
# generate_from_templates
# ------------------------------------------------------------------

def test_all_required_keys_returned():
    result = generate_from_templates(make_row())
    for key in REQUIRED_KEYS:
        assert key in result, f"Missing key: {key}"


def test_all_values_non_empty():
    result = generate_from_templates(make_row())
    for key in REQUIRED_KEYS:
        assert result[key].strip(), f"Empty value for: {key}"


def test_business_name_in_output():
    result = generate_from_templates(make_row(name="Sunset Dental"))
    found = any("Sunset Dental" in str(v) for v in result.values())
    assert found, "Business name not found in any outreach field"


def test_niche_in_output():
    result = generate_from_templates(make_row(niche="window tinting"))
    combined = " ".join(result.values())
    assert "window tinting" in combined.lower()


def test_city_in_output():
    result = generate_from_templates(make_row(city="Oakland"))
    combined = " ".join(result.values())
    assert "Oakland" in combined


def test_founder_name_used():
    result = generate_from_templates(make_row(), founder_name="Leon")
    combined = " ".join(result.values())
    assert "Leon" in combined


def test_sms_within_reasonable_length():
    result = generate_from_templates(make_row())
    # Templates are under 300 chars; 160 is strict but names vary
    assert len(result["sms_script"]) <= 300


def test_no_booking_situation():
    row = make_row(has_booking="False", website="https://example.com")
    result = generate_from_templates(row)
    assert result["cold_email_body"]


def test_no_website_situation():
    row = make_row(website="", has_booking="False", has_contact_form="False")
    result = generate_from_templates(row)
    assert result["cold_email_body"]


def test_strong_business_situation():
    row = make_row(rating="4.8", review_count="250",
                   has_booking="True", emails="owner@shop.com",
                   has_contact_form="True",
                   instagram="https://instagram.com/shop")
    result = generate_from_templates(row)
    assert result["cold_email_body"]


# ------------------------------------------------------------------
# OutreachGenerator (template mode)
# ------------------------------------------------------------------

def test_generator_no_api_key_uses_templates():
    gen = OutreachGenerator(api_key="", use_ai=False, founder_name="Leon")
    result = gen.generate(make_row())
    assert result["outreach_method"] == "template"
    for key in REQUIRED_KEYS:
        assert result[key].strip()


def test_generator_with_bad_api_key_falls_back():
    gen = OutreachGenerator(api_key="sk-fake-key", use_ai=True, founder_name="Leon")
    # Should not raise; falls back to templates
    result = gen.generate(make_row())
    for key in REQUIRED_KEYS:
        assert result[key].strip()


def test_generator_returns_outreach_method():
    gen = OutreachGenerator(api_key="", use_ai=False)
    result = gen.generate(make_row())
    assert "outreach_method" in result
    assert result["outreach_method"] in ("ai", "template")
