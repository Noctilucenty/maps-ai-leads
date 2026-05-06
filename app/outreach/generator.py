"""
Outreach generation: tries OpenAI first, falls back to built-in templates.
"""
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.outreach.templates import generate_from_templates
from app.utils.logging_utils import get_logger
from app.utils.text_utils import safe_str

logger = get_logger(__name__)

_OUTREACH_KEYS = [
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

_SYSTEM_PROMPT = """\
You are an expert cold outreach copywriter helping a founder sell AI automation services \
to local businesses (auto shops, med spas, dental clinics, home services, etc.).

Tone rules:
- Emails: 3–5 sentences max. Human, direct, founder-to-founder.
- NEVER say the business is struggling, failing, or behind.
- Lead with what they're doing well, then mention the opportunity.
- CTA: soft and simple — "15-minute call" or "I can send a short video."
- No buzzwords, no hype, no spam triggers (FREE, AMAZING, GUARANTEED).
- SMS: strictly under 155 characters.
- Instagram: casual, 2–3 sentences, emoji OK.
- LinkedIn: slightly more professional, 3–4 sentences.
- Call script: structured — INTRO / IF YES / IF NOT NOW / CLOSE.
- Loom script: 60-second arc — INTRO / HOOK / PROBLEM / SOLUTION / CTA.

Return ONLY valid JSON with exactly these keys (no extra commentary):
cold_email_subject, cold_email_body, follow_up_1, follow_up_2,
instagram_dm, linkedin_dm, sms_script, call_script, loom_video_script
"""


def _build_user_prompt(row: pd.Series, founder_name: str) -> str:
    socials = []
    for ch in ("instagram", "facebook", "linkedin", "x", "tiktok", "youtube"):
        if safe_str(row.get(ch, "")):
            socials.append(ch)
    social_summary = ", ".join(socials) if socials else "none"

    return (
        f"Business: {safe_str(row.get('name', ''))}\n"
        f"Type / niche: {safe_str(row.get('niche', 'local business'))}\n"
        f"City: {safe_str(row.get('city', ''))}\n"
        f"Google rating: {safe_str(row.get('rating', ''))} ⭐ "
        f"({safe_str(row.get('review_count', ''))} reviews)\n"
        f"Website: {safe_str(row.get('website', 'none'))}\n"
        f"Has booking system: {safe_str(row.get('has_booking', 'False'))}\n"
        f"Has contact form: {safe_str(row.get('has_contact_form', 'False'))}\n"
        f"Email found on site: {safe_str(row.get('emails', 'none'))}\n"
        f"Social presence: {social_summary}\n"
        f"Pain points: {safe_str(row.get('pain_points', 'unknown'))}\n"
        f"Recommended pitch: {safe_str(row.get('pitch_angle', ''))}\n"
        f"Offer to sell: {safe_str(row.get('recommended_offer', ''))}\n"
        f"Sender name: {founder_name}\n\n"
        "Write personalized outreach. Return ONLY the JSON object."
    )


def _parse_json(raw: str) -> Optional[dict]:
    """Extract and parse a JSON object from the model's response."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract {...} block from surrounding text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


class OutreachGenerator:
    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        use_ai: bool = True,
        founder_name: str = "the team",
    ) -> None:
        self.model = model
        self.founder_name = founder_name
        self._client = None

        if use_ai and api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=api_key)
                logger.info(f"OpenAI client ready (model: {model})")
            except ImportError:
                logger.warning(
                    "openai package not installed. "
                    "Run: pip install openai — falling back to templates."
                )
        elif use_ai and not api_key:
            logger.info("No OPENAI_API_KEY set — using template-based generation.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, row: pd.Series) -> dict:
        """Generate outreach for one lead row. Always returns all required keys."""
        if self._client:
            try:
                result = self._generate_with_ai(row)
                if result:
                    result["outreach_method"] = "ai"
                    return result
            except Exception as exc:
                logger.warning(
                    f"AI generation failed for "
                    f"{safe_str(row.get('name', '?'))}: {exc} — using templates."
                )

        result = generate_from_templates(row, self.founder_name)
        result["outreach_method"] = "template"
        return result

    def generate_batch(self, df: pd.DataFrame) -> list[dict]:
        results = []
        for _, row in df.iterrows():
            results.append(self.generate(row))
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_with_ai(self, row: pd.Series) -> Optional[dict]:
        prompt = _build_user_prompt(row, self.founder_name)

        for attempt in range(3):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=2000,
                )
                raw = response.choices[0].message.content or ""
                parsed = _parse_json(raw)

                if parsed is None:
                    logger.warning(f"Could not parse JSON (attempt {attempt + 1}/3)")
                    continue

                # Ensure all required keys are present
                missing = [k for k in _OUTREACH_KEYS if k not in parsed]
                if missing:
                    logger.warning(f"AI response missing keys: {missing}")
                    # Fill missing keys from templates
                    fallback = generate_from_templates(row, self.founder_name)
                    for k in missing:
                        parsed[k] = fallback[k]

                return parsed

            except Exception as exc:
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(f"OpenAI error (attempt {attempt + 1}/3): {exc}. Retrying in {wait}s…")
                    time.sleep(wait)
                else:
                    raise

        return None


# ------------------------------------------------------------------
# CRM defaults
# ------------------------------------------------------------------

def default_crm_fields(lead_score: int = 0) -> dict:
    from app.scoring.lead_score import determine_priority
    return {
        "status": "outreach_generated",
        "priority": determine_priority(lead_score),
        "last_contacted_at": "",
        "next_follow_up_at": "",
        "follow_up_count": "0",
        "notes": "",
        "owner_response": "",
        "outreach_generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
