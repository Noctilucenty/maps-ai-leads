"""
Lead scoring (0–100) with pain-point detection, pitch angle selection,
and recommended offer assignment.

Higher score = stronger opportunity for AI automation services.
A perfect score means: credible established business, weak digital automation.
"""
import pandas as pd

from app.utils.text_utils import clean_float, clean_int, safe_str


# ------------------------------------------------------------------
# Scoring weights
# ------------------------------------------------------------------

# Credibility signals (max ~35 pts)
_RATING_HIGH = 15       # 4.0–4.9 ★  (established, not an untouchable chain)
_RATING_MID = 8         # 3.5–3.9 ★
_RATING_LOW = 3         # any rating > 0
_REVIEWS_SWEET = 20     # 30–300 reviews (established SMB)
_REVIEWS_MID = 12       # 10–29 reviews
_REVIEWS_CHAIN = 8      # >300 (may be franchise — still worth pitching)
_REVIEWS_FEW = 5        # 1–9 reviews

# Opportunity signals (weaknesses = sales opportunities, max ~65 pts)
_HAS_WEBSITE = 10
_NO_WEBSITE = 5         # lower; different pitch needed
_NO_EMAIL = 20          # biggest opportunity: unreachable by email
_HAS_EMAIL = 5
_NO_FORM = 15           # no contact form
_NO_BOOKING = 10        # no booking system
_NO_SOCIAL = 10         # no social presence
_PARTIAL_SOCIAL = 5     # 1–2 channels only
_WEAK_TECH = 5          # GoDaddy / Wix — easy to pitch an upgrade


# ------------------------------------------------------------------
# Priority bands
# ------------------------------------------------------------------

def determine_priority(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    if score >= 35:
        return "low"
    return "skip"


# ------------------------------------------------------------------
# Pitch logic
# ------------------------------------------------------------------

def _pitch_and_offer(
    row: pd.Series,
    has_website: bool,
    has_email: bool,
    has_form: bool,
    has_booking: bool,
    rating: float,
    reviews: int,
) -> tuple[str, str]:
    niche = safe_str(row.get("niche", "")).lower() or "local"

    if not has_website:
        return (
            "No website: pitch AI-powered online presence + lead capture",
            "Website + AI Lead Capture Bundle",
        )

    # Phone-only: nothing digital works except phone
    if not has_email and not has_form and not has_booking:
        return (
            "Phone-only contact: pitch missed-call SMS recovery + AI booking",
            "AI Receptionist + Missed-Call SMS Recovery",
        )

    if not has_booking and not has_email:
        return (
            "No booking & no email: pitch AI booking system + lead capture form",
            "AI Booking System + Lead Capture",
        )

    if not has_booking:
        return (
            "No booking flow found: pitch AI booking + missed-call auto text",
            "AI Booking + Missed-Call Auto Text",
        )

    if has_booking and reviews < 20:
        return (
            "Has booking but low review count: pitch review request automation",
            "Review Request Automation",
        )

    if rating >= 4.5 and reviews >= 100:
        return (
            "Strong reputation: pitch overflow call handling + after-hours conversion",
            "AI Receptionist + After-Hours Lead Capture",
        )

    if not has_email and not has_form:
        return (
            "Weak contact path: pitch AI receptionist + SMS lead capture",
            "AI Receptionist + SMS Lead Capture",
        )

    return (
        "General fit: pitch AI receptionist + quote capture",
        "AI Receptionist + Quote Capture",
    )


# ------------------------------------------------------------------
# Main scoring function
# ------------------------------------------------------------------

def score_lead(row: pd.Series) -> dict:
    """
    Score a lead row and return a dict with:
      lead_score       (int 0–100)
      pain_points      (semicolon-separated string)
      pitch_angle      (str)
      recommended_offer (str)
      priority         (high/medium/low/skip)
    """
    score = 0
    pain_points: list[str] = []

    # Disqualify non-operational businesses immediately
    status = safe_str(row.get("business_status", "")).upper()
    if status and status != "OPERATIONAL":
        return {
            "lead_score": 0,
            "pain_points": "Business not operational",
            "pitch_angle": "N/A",
            "recommended_offer": "N/A",
            "priority": "skip",
        }

    # --- Credibility ---
    rating = clean_float(row.get("rating", 0))
    reviews = clean_int(row.get("review_count", 0))

    if 4.0 <= rating <= 4.9:
        score += _RATING_HIGH
    elif 3.5 <= rating < 4.0:
        score += _RATING_MID
    elif rating > 0:
        score += _RATING_LOW

    if 30 <= reviews <= 300:
        score += _REVIEWS_SWEET
    elif 10 <= reviews < 30:
        score += _REVIEWS_MID
    elif reviews > 300:
        score += _REVIEWS_CHAIN
    elif reviews > 0:
        score += _REVIEWS_FEW

    # --- Opportunity ---
    website = safe_str(row.get("website", ""))
    has_website = bool(website)
    if has_website:
        score += _HAS_WEBSITE
    else:
        score += _NO_WEBSITE
        pain_points.append("No website")

    emails = safe_str(row.get("emails", ""))
    has_email = bool(emails)
    if not has_email:
        score += _NO_EMAIL
        pain_points.append("No email contact visible")
    else:
        score += _HAS_EMAIL

    has_form = safe_str(row.get("has_contact_form", "False")) == "True"
    if not has_form:
        score += _NO_FORM
        pain_points.append("No contact form")

    has_booking = safe_str(row.get("has_booking", "False")) == "True"
    if not has_booking:
        score += _NO_BOOKING
        pain_points.append("No online booking system")

    # Social signals
    social_count = sum(
        1
        for key in ("instagram", "facebook", "linkedin", "x", "tiktok", "youtube")
        if safe_str(row.get(key, ""))
    )
    if social_count == 0:
        score += _NO_SOCIAL
        pain_points.append("No social media presence")
    elif social_count <= 2:
        score += _PARTIAL_SOCIAL

    # Tech stack signals
    tech = safe_str(row.get("tech_stack", "")).lower()
    if any(weak in tech for weak in ("godaddy", "wix")):
        score += _WEAK_TECH
        pain_points.append("Outdated website platform")

    # Cap 0–100
    lead_score = min(100, max(0, score))
    priority = determine_priority(lead_score)

    pitch_angle, recommended_offer = _pitch_and_offer(
        row, has_website, has_email, has_form, has_booking, rating, reviews
    )

    return {
        "lead_score": lead_score,
        "pain_points": ";".join(pain_points),
        "pitch_angle": pitch_angle,
        "recommended_offer": recommended_offer,
        "priority": priority,
    }


def score_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply score_lead to every row and add result columns to df."""
    score_cols = pd.DataFrame(df.apply(score_lead, axis=1).tolist())
    for col in score_cols.columns:
        df[col] = score_cols[col].values
    return df
