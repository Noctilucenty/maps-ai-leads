"""Tests for lead scoring logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from app.scoring.lead_score import determine_priority, score_lead


def row(**kwargs) -> pd.Series:
    defaults = {
        "name": "Test Shop",
        "business_status": "OPERATIONAL",
        "rating": "4.5",
        "review_count": "80",
        "website": "https://example.com",
        "emails": "",
        "has_contact_form": "False",
        "has_booking": "False",
        "instagram": "",
        "facebook": "",
        "linkedin": "",
        "x": "",
        "tiktok": "",
        "youtube": "",
        "tech_stack": "",
        "niche": "auto repair",
        "city": "San Jose",
    }
    defaults.update(kwargs)
    return pd.Series(defaults)


# ------------------------------------------------------------------
# Basic correctness
# ------------------------------------------------------------------

def test_score_in_valid_range():
    result = score_lead(row())
    assert 0 <= result["lead_score"] <= 100


def test_all_required_keys_present():
    result = score_lead(row())
    assert "lead_score" in result
    assert "pain_points" in result
    assert "pitch_angle" in result
    assert "recommended_offer" in result
    assert "priority" in result


def test_non_operational_scores_zero():
    result = score_lead(row(business_status="CLOSED_PERMANENTLY"))
    assert result["lead_score"] == 0
    assert result["priority"] == "skip"


def test_non_operational_with_no_status_does_not_disqualify():
    # Empty status should NOT disqualify (we don't always get this field)
    result = score_lead(row(business_status=""))
    assert result["lead_score"] > 0


# ------------------------------------------------------------------
# Pain point detection
# ------------------------------------------------------------------

def test_no_email_adds_pain_point():
    result = score_lead(row(emails=""))
    assert "No email contact visible" in result["pain_points"]


def test_has_email_no_pain_point():
    result = score_lead(row(emails="owner@shop.com"))
    assert "No email contact visible" not in result["pain_points"]


def test_no_website_pain_point():
    result = score_lead(row(website=""))
    assert "No website" in result["pain_points"]


def test_no_booking_pain_point():
    result = score_lead(row(has_booking="False"))
    assert "No online booking system" in result["pain_points"]


def test_no_contact_form_pain_point():
    result = score_lead(row(has_contact_form="False"))
    assert "No contact form" in result["pain_points"]


def test_no_social_pain_point():
    result = score_lead(row())  # defaults have no socials
    assert "No social media presence" in result["pain_points"]


def test_godaddy_tech_adds_pain_point():
    result = score_lead(row(tech_stack="godaddy"))
    assert "Outdated website platform" in result["pain_points"]


# ------------------------------------------------------------------
# Scoring relative comparisons
# ------------------------------------------------------------------

def test_phone_only_scores_higher_than_well_equipped():
    """A phone-only business should score higher (more opportunity) than
    one with email, form, booking, and socials."""
    phone_only = score_lead(row(
        emails="", has_contact_form="False", has_booking="False",
        instagram="", facebook="",
    ))
    well_equipped = score_lead(row(
        emails="owner@shop.com", has_contact_form="True", has_booking="True",
        instagram="https://instagram.com/shop", facebook="https://facebook.com/shop",
    ))
    assert phone_only["lead_score"] > well_equipped["lead_score"]


def test_higher_reviews_sweet_spot_scores_more_than_zero_reviews():
    no_reviews = score_lead(row(review_count="0"))
    sweet_spot = score_lead(row(review_count="100"))
    assert sweet_spot["lead_score"] > no_reviews["lead_score"]


def test_has_booking_reduces_score():
    without_booking = score_lead(row(has_booking="False"))
    with_booking = score_lead(row(has_booking="True"))
    assert without_booking["lead_score"] > with_booking["lead_score"]


# ------------------------------------------------------------------
# Priority bands
# ------------------------------------------------------------------

def test_priority_high_for_high_score():
    assert determine_priority(80) == "high"
    assert determine_priority(100) == "high"


def test_priority_medium():
    assert determine_priority(60) == "medium"
    assert determine_priority(74) == "medium"


def test_priority_low():
    assert determine_priority(40) == "low"


def test_priority_skip():
    assert determine_priority(0) == "skip"
    assert determine_priority(20) == "skip"


# ------------------------------------------------------------------
# Pitch angle
# ------------------------------------------------------------------

def test_phone_only_pitch():
    result = score_lead(row(emails="", has_contact_form="False", has_booking="False"))
    assert "missed-call" in result["pitch_angle"].lower() or "sms" in result["pitch_angle"].lower()


def test_no_website_pitch():
    result = score_lead(row(website=""))
    assert "website" in result["pitch_angle"].lower() or "presence" in result["pitch_angle"].lower()


def test_has_booking_low_reviews_pitch():
    result = score_lead(row(has_booking="True", review_count="5"))
    assert "review" in result["pitch_angle"].lower()
