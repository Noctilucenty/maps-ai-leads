"""
Centralized configuration loaded from environment variables / .env file.
Copy .env.example → .env and fill in your keys.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; set env vars manually if not installed

GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
FOUNDER_NAME: str = os.getenv("FOUNDER_NAME", "the team")
REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "15"))
RATE_LIMIT_SECONDS: float = float(os.getenv("RATE_LIMIT_SECONDS", "1.2"))
DEFAULT_MAX_RESULTS: int = int(os.getenv("DEFAULT_MAX_RESULTS", "60"))

# Directory layout
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
ENRICHED_DIR = DATA_DIR / "enriched"
OUTREACH_DIR = DATA_DIR / "outreach"
CAMPAIGNS_DIR = DATA_DIR / "campaigns"

for _d in (RAW_DIR, ENRICHED_DIR, OUTREACH_DIR, CAMPAIGNS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
