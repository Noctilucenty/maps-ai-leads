"""
Website enrichment — scrapes business websites for emails, socials, booking signals,
tech stack, and contact paths. Also exposes enrich_dataframe() for batch use.
"""
import concurrent.futures
import re
import socket
import time
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

EMAIL_REGEX = re.compile(r'(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b')
PHONE_REGEX = re.compile(
    r'(?:(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4})'
)
BAD_EMAIL_PREFIXES = {
    "png", "jpg", "jpeg", "webp", "svg", "gif",
    "css", "js", "ico", "woff", "woff2",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
CONTACT_KEYWORDS = [
    "contact", "about", "book", "booking", "appointment", "appointments",
    "schedule", "reservation", "reserve", "service", "services", "support",
]
SOCIAL_HOSTS: Dict[str, str] = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "linkedin.com": "linkedin",
    "x.com": "x",
    "twitter.com": "x",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
}
BOOKING_KEYWORDS = [
    "book now", "schedule", "appointment", "reserve", "reservation",
    "book online", "request appointment", "book a", "schedule a",
]
CONTACT_FORM_KEYWORDS = [
    "contact us", "send us a message", "get in touch", "message us", "submit",
]
TECH_PATTERNS: Dict[str, List[str]] = {
    "wordpress": ["wp-content", "wp-includes", "wordpress"],
    "wix": ["wix.com", "static.wixstatic.com", "wix-image"],
    "squarespace": ["squarespace.com", "static.squarespace.com", "sqsp"],
    "shopify": ["cdn.shopify.com", "shopify"],
    "godaddy": ["godaddy", "secureserver.net"],
    "webflow": ["webflow", "assets.website-files.com"],
}


# ------------------------------------------------------------------
# URL helpers
# ------------------------------------------------------------------

def normalize_website(url: str) -> str:
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return url if parsed.netloc else ""


def is_private_host(hostname: str) -> bool:
    try:
        ip = socket.gethostbyname(hostname)
        parts = [int(x) for x in ip.split(".")]
        if len(parts) != 4:
            return True
        a, b = parts[0], parts[1]
        return (
            a == 10
            or a == 127
            or (a == 169 and b == 254)
            or (a == 172 and 16 <= b <= 31)
            or (a == 192 and b == 168)
        )
    except Exception:
        return True


def safe_same_domain(base_url: str, candidate_url: str) -> bool:
    try:
        base_host = urlparse(base_url).netloc.lower().lstrip("www.")
        cand_host = urlparse(candidate_url).netloc.lower().lstrip("www.")
        return base_host == cand_host
    except Exception:
        return False


# ------------------------------------------------------------------
# SiteEnricher
# ------------------------------------------------------------------

class SiteEnricher:
    def __init__(
        self,
        timeout: int = 15,
        max_pages: int = 5,
        delay: float = 0.4,
        max_workers: int = 5,
    ) -> None:
        self.timeout = timeout
        self.max_pages = max_pages
        self.delay = delay
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch(self, url: str) -> Optional[requests.Response]:
        try:
            resp = self.session.get(
                url, timeout=self.timeout, allow_redirects=True
            )
            ct = resp.headers.get("Content-Type", "").lower()
            if "text/html" not in ct and "application/xhtml+xml" not in ct:
                return None
            if resp.status_code >= 400:
                return None
            return resp
        except requests.RequestException:
            return None

    def extract_emails(self, text: str) -> Set[str]:
        emails: Set[str] = set()
        for email in EMAIL_REGEX.findall(text or ""):
            email = email.strip(".,;:()[]{}<>").lower()
            local = email.split("@")[0]
            if local in BAD_EMAIL_PREFIXES:
                continue
            if email.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")):
                continue
            emails.add(email)
        return emails

    def extract_socials(self, soup: BeautifulSoup, base_url: str) -> Dict[str, str]:
        found = {v: "" for v in SOCIAL_HOSTS.values()}
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            absolute = urljoin(base_url, href)
            host = urlparse(absolute).netloc.lower()
            for domain, label in SOCIAL_HOSTS.items():
                if domain in host and not found[label]:
                    found[label] = absolute
        return found

    def extract_candidate_pages(
        self, soup: BeautifulSoup, base_url: str
    ) -> List[str]:
        candidates = []
        seen: Set[str] = set()

        # fixed path guesses
        for path in [
            "/contact", "/contact-us", "/about", "/about-us",
            "/book", "/booking", "/appointments", "/schedule",
            "/reservation", "/reserve",
        ]:
            candidate = urljoin(base_url, path)
            if safe_same_domain(base_url, candidate) and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)

        # link-discovered pages
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(" ", strip=True).lower()
            absolute = urljoin(base_url, href)
            if not absolute.startswith(("http://", "https://")):
                continue
            if not safe_same_domain(base_url, absolute):
                continue
            combined = f"{text} {href.lower()}"
            if any(kw in combined for kw in CONTACT_KEYWORDS):
                if absolute not in seen:
                    seen.add(absolute)
                    candidates.append(absolute)

        return candidates[: self.max_pages - 1]

    def detect_tech_stack(self, html: str) -> List[str]:
        html_low = (html or "").lower()
        return [
            tech
            for tech, patterns in TECH_PATTERNS.items()
            if any(p in html_low for p in patterns)
        ]

    def detect_booking(
        self, soup: BeautifulSoup, text: str
    ) -> Tuple[bool, str]:
        text_low = (text or "").lower()
        for kw in BOOKING_KEYWORDS:
            if kw in text_low:
                return True, kw
        for a in soup.find_all("a", href=True):
            combined = f"{a['href'].lower()} {a.get_text(' ', strip=True).lower()}"
            for kw in BOOKING_KEYWORDS:
                if kw in combined:
                    return True, kw
        return False, ""

    def detect_contact_form(self, soup: BeautifulSoup, text: str) -> bool:
        if soup.find("form") is not None:
            return True
        text_low = (text or "").lower()
        return any(kw in text_low for kw in CONTACT_FORM_KEYWORDS)

    def analyze_site(self, website: str) -> Dict[str, str]:
        result: Dict[str, str] = {
            "final_url": "",
            "emails": "",
            "phone_found_on_site": "",
            "contact_page": "",
            "about_page": "",
            "booking_page": "",
            "instagram": "",
            "facebook": "",
            "linkedin": "",
            "x": "",
            "tiktok": "",
            "youtube": "",
            "has_contact_form": "False",
            "has_booking": "False",
            "booking_hint": "",
            "tech_stack": "",
            "crawl_status": "failed",
        }

        website = normalize_website(website)
        if not website:
            result["crawl_status"] = "no_website"
            return result

        parsed = urlparse(website)
        if not parsed.netloc or is_private_host(parsed.netloc):
            result["crawl_status"] = "unsafe_host"
            return result

        homepage_resp = self.fetch(website)
        if homepage_resp is None:
            result["crawl_status"] = "homepage_failed"
            return result

        final_url = homepage_resp.url
        result["final_url"] = final_url

        homepage_soup = BeautifulSoup(homepage_resp.text, "lxml")
        pages_to_visit = [final_url] + self.extract_candidate_pages(
            homepage_soup, final_url
        )

        visited: Set[str] = set()
        all_emails: Set[str] = set()
        tech_found: Set[str] = set()
        phone_found = ""
        socials = {v: "" for v in SOCIAL_HOSTS.values()}
        has_contact_form = False
        has_booking = False
        booking_hint = ""

        for page_url in pages_to_visit[: self.max_pages]:
            if page_url in visited:
                continue
            visited.add(page_url)

            resp = (
                homepage_resp
                if page_url == final_url
                else self.fetch(page_url)
            )
            if resp is None:
                continue

            html = resp.text
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(" ", strip=True)

            all_emails.update(self.extract_emails(html + "\n" + text))

            if not phone_found:
                m = PHONE_REGEX.search(text)
                if m:
                    phone_found = m.group(0)

            page_socials = self.extract_socials(soup, resp.url)
            for key, val in page_socials.items():
                if val and not socials[key]:
                    socials[key] = val

            for tech in self.detect_tech_stack(html):
                tech_found.add(tech)

            if not has_contact_form and self.detect_contact_form(soup, text):
                has_contact_form = True

            if not has_booking:
                detected, hint = self.detect_booking(soup, text)
                if detected:
                    has_booking = True
                    booking_hint = hint

            lower_url = resp.url.lower()
            if not result["contact_page"] and "contact" in lower_url:
                result["contact_page"] = resp.url
            if not result["about_page"] and "about" in lower_url:
                result["about_page"] = resp.url
            if not result["booking_page"] and any(
                k in lower_url for k in ["book", "appoint", "schedule", "reserv"]
            ):
                result["booking_page"] = resp.url

            time.sleep(self.delay)

        result.update({
            "emails": ";".join(sorted(all_emails)),
            "phone_found_on_site": phone_found,
            "has_contact_form": str(has_contact_form),
            "has_booking": str(has_booking),
            "booking_hint": booking_hint,
            "tech_stack": ";".join(sorted(tech_found)),
            "crawl_status": "ok",
            **socials,
        })
        return result


# ------------------------------------------------------------------
# Batch enrichment
# ------------------------------------------------------------------

def _enrich_one(enricher: SiteEnricher, row: pd.Series) -> Dict[str, str]:
    website = str(row.get("website", "") or "").strip()
    return enricher.analyze_site(website)


def enrich_dataframe(
    df: pd.DataFrame,
    timeout: int = 15,
    max_pages: int = 5,
    delay: float = 0.4,
    max_workers: int = 5,
) -> pd.DataFrame:
    enricher = SiteEnricher(
        timeout=timeout,
        max_pages=max_pages,
        delay=delay,
        max_workers=max_workers,
    )

    empty_result: Dict[str, str] = {
        "final_url": "", "emails": "", "phone_found_on_site": "",
        "contact_page": "", "about_page": "", "booking_page": "",
        "instagram": "", "facebook": "", "linkedin": "",
        "x": "", "tiktok": "", "youtube": "",
        "has_contact_form": "False", "has_booking": "False",
        "booking_hint": "", "tech_stack": "", "crawl_status": "worker_error",
    }

    results: List[Optional[Dict]] = [None] * len(df)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_enrich_one, enricher, df.iloc[i]): i
            for i in range(len(df))
        }
        for count, future in enumerate(
            concurrent.futures.as_completed(futures), start=1
        ):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.warning(f"Worker error on row {idx}: {exc}")
                results[idx] = dict(empty_result)

            if count % 10 == 0:
                logger.info(f"  enriched {count}/{len(df)} websites…")

    enrich_df = pd.DataFrame(results)
    return pd.concat([df.reset_index(drop=True), enrich_df], axis=1)
