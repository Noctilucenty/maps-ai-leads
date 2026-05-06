"""
Fallback template-based outreach generation.
Used when no OpenAI key is configured, or as a safety net when the API call fails.

Templates are intentionally short, human, and positive-framed.
"""
import random
from typing import Dict

import pandas as pd

from app.utils.text_utils import clean_float, clean_int, safe_str


# ------------------------------------------------------------------
# Email templates — keyed by situation
# ------------------------------------------------------------------

_EMAIL_TEMPLATES: Dict[str, list] = {
    "phone_only": [
        {
            "subject": "Quick question — {name}",
            "body": (
                "Hi,\n\n"
                "Came across {name} while looking at {niche} shops in {city} — "
                "{rating} stars with {review_count} reviews, that's a solid reputation.\n\n"
                "Quick question: are you capturing missed calls automatically? "
                "Most {niche} businesses lose 20–30% of their leads to voicemail, "
                "especially after hours.\n\n"
                "Would it be worth 15 minutes to see how we handle that for similar businesses?\n\n"
                "{founder_name}\n\n"
                "P.S. Happy to send a 3-minute video walkthrough instead if that's easier."
            ),
        },
        {
            "subject": "{name} — one thing worth a quick look",
            "body": (
                "Hi,\n\n"
                "Found {name} while researching {niche} businesses in {city}. "
                "{review_count} reviews at {rating} stars — clearly you're doing a lot right.\n\n"
                "One gap I noticed: there's no easy email or contact path visible, "
                "which means customers who visit outside business hours probably don't convert.\n\n"
                "I help {niche} shops add automated follow-up so those leads don't slip through. "
                "Worth a 15-minute call?\n\n"
                "{founder_name}"
            ),
        },
    ],
    "no_booking": [
        {
            "subject": "Booking automation for {name}?",
            "body": (
                "Hi,\n\n"
                "Found {name} on Google — {rating} stars and {review_count} reviews. "
                "You clearly know how to take care of customers.\n\n"
                "I noticed there's no online booking on your site. For {niche} businesses, "
                "adding an AI booking flow + missed-call follow-up typically captures "
                "20–40% more leads without adding any manual work.\n\n"
                "Would a 15-minute conversation be worth it?\n\n"
                "{founder_name}"
            ),
        },
        {
            "subject": "Saw your {niche} in {city} — quick thought",
            "body": (
                "Hey,\n\n"
                "Came across {name} while looking at top-rated {niche} shops in {city}. "
                "Impressive what you've built.\n\n"
                "Quick thought: are you set up to capture customers who visit your site "
                "at 9pm and don't see a way to book? That's usually the biggest gap "
                "for businesses your size.\n\n"
                "I help {niche} shops in {city} fix exactly that — happy to show you "
                "in under 15 minutes.\n\n"
                "{founder_name}"
            ),
        },
    ],
    "has_booking_weak_reviews": [
        {
            "subject": "{name} — one thing that could double your reviews",
            "body": (
                "Hi,\n\n"
                "Found {name} while searching for {niche} in {city} — you already have "
                "a booking system set up, which puts you ahead of most.\n\n"
                "One thing that would amplify it: automating review requests after each job. "
                "Most {niche} businesses that do this see their review count grow 2–3x "
                "within 90 days, which also boosts your Google ranking.\n\n"
                "Worth a quick conversation?\n\n"
                "{founder_name}"
            ),
        },
    ],
    "strong_no_capture": [
        {
            "subject": "One idea for {name}",
            "body": (
                "Hi,\n\n"
                "I came across {name} — {rating} stars with {review_count}+ reviews. "
                "That kind of reputation takes real work and it shows.\n\n"
                "I help {niche} businesses like yours capture the leads that slip through "
                "after hours — missed-call SMS, AI booking, and automated follow-up. "
                "With your reputation, you'd convert those inquiries really well.\n\n"
                "Would a quick 15-minute conversation be worth it?\n\n"
                "{founder_name}"
            ),
        },
    ],
    "no_website": [
        {
            "subject": "Quick question for {name}",
            "body": (
                "Hi,\n\n"
                "Came across {name} while researching {niche} businesses in {city} — "
                "looks like a great operation.\n\n"
                "Quick question: are you currently capturing leads from customers "
                "who search online but can't find your contact info easily? "
                "Most businesses without a web presence lose a significant chunk of "
                "local search traffic.\n\n"
                "I help {niche} businesses get a simple, lead-capturing website up fast. "
                "Worth a quick call?\n\n"
                "{founder_name}"
            ),
        },
    ],
    "default": [
        {
            "subject": "Idea for {name}",
            "body": (
                "Hi,\n\n"
                "Found {name} while looking at {niche} businesses in {city} — "
                "{rating} stars, {review_count} reviews. You're clearly running a solid operation.\n\n"
                "I help {niche} shops automate the parts that usually fall through the cracks — "
                "missed calls, booking follow-up, lead capture, review requests.\n\n"
                "Would it be worth 15 minutes to see if any of that fits?\n\n"
                "{founder_name}"
            ),
        },
    ],
}

# Follow-ups (situation-agnostic)
_FOLLOW_UP_1 = (
    "Hey,\n\n"
    "Just bumping this up — still curious if capturing more leads automatically "
    "would be useful for {name}.\n\n"
    "No worries if timing is off. Happy to connect whenever works.\n\n"
    "{founder_name}"
)

_FOLLOW_UP_2 = (
    "Hi,\n\n"
    "Last follow-up, I promise.\n\n"
    "I put together a quick 3-minute overview of how we help {niche} businesses in {city} "
    "automate their lead follow-up — happy to send it over if you'd like a low-pressure look.\n\n"
    "Either way, keep up the great work at {name}!\n\n"
    "{founder_name}"
)

_INSTAGRAM_DM = (
    "Hey! Came across {name} while looking at {niche} shops in {city} — "
    "{review_count} reviews is seriously impressive. 💪\n\n"
    "I help shops like yours capture more leads automatically (missed calls, bookings, follow-ups). "
    "Worth a quick chat or want me to send a short video?"
)

_LINKEDIN_DM = (
    "Hi! Found {name} while researching {niche} businesses in {city}.\n\n"
    "{review_count} reviews at {rating} stars — that's a strong reputation in a competitive market.\n\n"
    "I help similar businesses add AI tools that capture leads they'd otherwise miss "
    "(after-hours calls, site visitors without a clear booking path, etc.). "
    "Would a 15-min call be worth exploring?\n\n"
    "Happy to share how we've helped similar {niche} shops."
)

_SMS_SCRIPT = (
    "Hi! Saw {name} in {city} — {rating}★, {review_count} reviews. "
    "Help {niche}s book more automatically. Quick chat? -{founder_name}"
)

_CALL_SCRIPT = (
    "INTRO:\n"
    '"Hi, is this {name}? My name is {founder_name} — I help {niche} businesses in {city} '
    'capture more leads and bookings automatically. Do you have 2 minutes?"\n\n'
    "IF YES:\n"
    '"Great. I was looking at your business online — {review_count} reviews at {rating} stars, '
    "which is genuinely impressive. What I do is help businesses like yours capture the leads "
    "that slip through — after-hours calls, website visitors who don't see an easy way to book. "
    'Does that sound like something worth a quick 15-minute conversation?"\n\n'
    "IF INTERESTED:\n"
    '"Perfect. When works best for you? I can also send a 3-minute video if you\'d prefer '
    'to see it first."\n\n'
    "IF NOT RIGHT NOW:\n"
    '"Totally understand. Can I send a quick video that shows exactly how it works? '
    'No strings attached — if it\'s not relevant, no pressure at all."\n\n'
    "CLOSE:\n"
    '"Thanks so much for your time. Have a great day!"'
)

_LOOM_SCRIPT = (
    "INTRO (0:00–0:10):\n"
    '"Hey {name} team, {founder_name} here. Quick video — I spotted one thing that could '
    'help you capture more customers without changing how you operate."\n\n'
    "HOOK (0:10–0:30):\n"
    '"I found your business while searching for {niche} shops in {city}. '
    "{review_count} reviews at {rating} stars — that takes real work and it's clear you've earned it.\"\n\n"
    "PROBLEM (0:30–1:00):\n"
    '"The one opportunity I spotted: {pitch_angle}. For most {niche} businesses, that means '
    "missed inquiries — customers who call after hours or visit the site and don't find "
    'an easy next step."\n\n'
    "SOLUTION (1:00–1:45):\n"
    '"What we do is set up AI tools that handle this automatically — missed-call texts '
    "within 60 seconds, a simple booking flow, and follow-up sequences that run without "
    'you touching anything."\n\n'
    "DEMO (1:45–2:30):\n"
    '"Let me show you a quick example of how this looks for a similar {niche} business…"\n'
    "[screen recording here]\n\n"
    "CTA (2:30–3:00):\n"
    '"If this looks interesting, I\'d love 15 minutes on the calendar — link below. '
    "No pitch deck, just a quick conversation to see if it makes sense for {name}. Thanks!\""
)


# ------------------------------------------------------------------
# Situation selector
# ------------------------------------------------------------------

def _detect_situation(row: pd.Series) -> str:
    website = safe_str(row.get("website", ""))
    emails = safe_str(row.get("emails", ""))
    has_form = safe_str(row.get("has_contact_form", "False")) == "True"
    has_booking = safe_str(row.get("has_booking", "False")) == "True"
    rating = clean_float(row.get("rating", 0))
    reviews = clean_int(row.get("review_count", 0))

    if not website:
        return "no_website"
    if not emails and not has_form and not has_booking:
        return "phone_only"
    if not has_booking and not emails:
        return "no_booking"
    if not has_booking:
        return "no_booking"
    if has_booking and reviews < 20:
        return "has_booking_weak_reviews"
    if rating >= 4.5 and reviews >= 100:
        return "strong_no_capture"
    return "default"


# ------------------------------------------------------------------
# Template renderer
# ------------------------------------------------------------------

def _render(template: str, row: pd.Series, founder_name: str) -> str:
    return template.format(
        name=safe_str(row.get("name", "your business")),
        niche=safe_str(row.get("niche", "local business")),
        city=safe_str(row.get("city", "your area")),
        rating=safe_str(row.get("rating", "4.5")),
        review_count=safe_str(row.get("review_count", "many")),
        website=safe_str(row.get("website", "")),
        pitch_angle=safe_str(row.get("pitch_angle", "AI automation")),
        founder_name=founder_name,
    )


def generate_from_templates(row: pd.Series, founder_name: str = "the team") -> dict:
    """Return all outreach fields using built-in templates (no API needed)."""
    situation = _detect_situation(row)
    templates = _EMAIL_TEMPLATES.get(situation, _EMAIL_TEMPLATES["default"])
    chosen = random.choice(templates)

    def r(t: str) -> str:
        return _render(t, row, founder_name)

    return {
        "cold_email_subject": r(chosen["subject"]),
        "cold_email_body": r(chosen["body"]),
        "follow_up_1": r(_FOLLOW_UP_1),
        "follow_up_2": r(_FOLLOW_UP_2),
        "instagram_dm": r(_INSTAGRAM_DM),
        "linkedin_dm": r(_LINKEDIN_DM),
        "sms_script": r(_SMS_SCRIPT),
        "call_script": r(_CALL_SCRIPT),
        "loom_video_script": r(_LOOM_SCRIPT),
    }
