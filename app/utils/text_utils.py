import re


def clean_int(value) -> int:
    try:
        if isinstance(value, float):
            import math
            if math.isnan(value):
                return 0
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def clean_float(value) -> float:
    try:
        if isinstance(value, float):
            import math
            if math.isnan(value):
                return 0.0
        return float(str(value).strip())
    except Exception:
        return 0.0


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def truncate(text: str, max_len: int = 300) -> str:
    text = str(text or "").strip()
    return text[:max_len] + "…" if len(text) > max_len else text


def safe_str(value) -> str:
    """Return a clean string, treating None/NaN/float NaN as empty."""
    if value is None:
        return ""
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass
    return str(value).strip()
