import argparse
import concurrent.futures
import re
import socket
import time
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


EMAIL_REGEX = re.compile(r'(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b')
PHONE_REGEX = re.compile(r'(?:(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4})')
BAD_EMAIL_PREFIXES = {
    "png", "jpg", "jpeg", "webp", "svg", "gif", "css", "js", "ico", "woff", "woff2"
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
    "schedule", "reservation", "reserve", "service", "services", "support"
]
SOCIAL_HOSTS = {
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
    "book online", "request appointment"
]
CONTACT_FORM_KEYWORDS = [
    "contact us", "send us a message", "get in touch", "message us", "submit"
]
TECH_PATTERNS = {
    "wordpress": [
        "wp-content", "wp-includes", "wordpress"
    ],
    "wix": [
        "wix.com", "static.wixstatic.com", "wix-image"
    ],
    "squarespace": [
        "squarespace.com", "static.squarespace.com", "sqsp"
    ],
    "shopify": [
        "cdn.shopify.com", "shopify"
    ],
    "godaddy": [
        "godaddy", "secureserver.net"
    ],
    "webflow": [
        "webflow", "assets.website-files.com"
    ],
}


def normalize_website(url: str) -> str:
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    return url


def is_private_host(hostname: str) -> bool:
    try:
        ip = socket.gethostbyname(hostname)
        parts = ip.split(".")
        if len(parts) != 4:
            return True
        a, b, _, _ = [int(x) for x in parts]
        if a == 10:
            return True
        if a == 127:
            return True
        if a == 169 and b == 254:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        return False
    except Exception:
        return True


def safe_same_domain(base_url: str, candidate_url: str) -> bool:
    try:
        base_host = urlparse(base_url).netloc.lower().lstrip("www.")
        cand_host = urlparse(candidate_url).netloc.lower().lstrip("www.")
        return base_host == cand_host
    except Exception:
        return False


class SiteEnricher:
    def __init__(
        self,
        timeout: int = 15,
        max_pages: int = 5,
        delay: float = 0.5,
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
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return None
            if response.status_code >= 400:
                return None
            return response
        except requests.RequestException:
            return None

    def extract_emails(self, text: str) -> Set[str]:
        emails = set()
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

    def extract_candidate_pages(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        candidates = []
        seen = set()

        # common fixed guesses first
        guessed_paths = [
            "/contact", "/contact-us", "/about", "/about-us",
            "/book", "/booking", "/appointments", "/schedule",
            "/reservation", "/reserve"
        ]
        for path in guessed_paths:
            candidate = urljoin(base_url, path)
            if safe_same_domain(base_url, candidate) and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)

        # then link-discovered pages
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(" ", strip=True).lower()
            absolute = urljoin(base_url, href)

            if not absolute.startswith(("http://", "https://")):
                continue
            if not safe_same_domain(base_url, absolute):
                continue

            combined = f"{text} {href.lower()}"
            if any(keyword in combined for keyword in CONTACT_KEYWORDS):
                if absolute not in seen:
                    seen.add(absolute)
                    candidates.append(absolute)

        return candidates[: self.max_pages - 1]

    def detect_tech_stack(self, html: str) -> List[str]:
        html_low = (html or "").lower()
        found = []
        for tech, patterns in TECH_PATTERNS.items():
            if any(pattern in html_low for pattern in patterns):
                found.append(tech)
        return found

    def detect_booking(self, soup: BeautifulSoup, text: str) -> Tuple[bool, str]:
        text_low = (text or "").lower()

        for keyword in BOOKING_KEYWORDS:
            if keyword in text_low:
                return True, keyword

        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            a_text = a.get_text(" ", strip=True).lower()
            combined = f"{href} {a_text}"
            for keyword in BOOKING_KEYWORDS:
                if keyword in combined:
                    return True, keyword

        return False, ""

    def detect_contact_form(self, soup: BeautifulSoup, text: str) -> bool:
        if soup.find("form") is not None:
            return True

        text_low = (text or "").lower()
        return any(keyword in text_low for keyword in CONTACT_FORM_KEYWORDS)

    def analyze_site(self, website: str) -> Dict[str, str]:
        result = {
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

        pages_to_visit = [final_url]
        homepage_soup = BeautifulSoup(homepage_resp.text, "lxml")
        pages_to_visit.extend(self.extract_candidate_pages(homepage_soup, final_url))

        visited = set()
        all_emails: Set[str] = set()
        tech_stack_found: Set[str] = set()
        phone_found = ""
        socials = {v: "" for v in SOCIAL_HOSTS.values()}
        has_contact_form = False
        has_booking = False
        booking_hint = ""

        for page_url in pages_to_visit[: self.max_pages]:
            if page_url in visited:
                continue
            visited.add(page_url)

            resp = homepage_resp if page_url == final_url else self.fetch(page_url)
            if resp is None:
                continue

            html = resp.text
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(" ", strip=True)

            emails = self.extract_emails(html + "\n" + text)
            all_emails.update(emails)

            if not phone_found:
                match = PHONE_REGEX.search(text)
                if match:
                    phone_found = match.group(0)

            page_socials = self.extract_socials(soup, resp.url)
            for key, value in page_socials.items():
                if value and not socials[key]:
                    socials[key] = value

            for tech in self.detect_tech_stack(html):
                tech_stack_found.add(tech)

            if self.detect_contact_form(soup, text):
                has_contact_form = True

            booking_detected, hint = self.detect_booking(soup, text)
            if booking_detected:
                has_booking = True
                if not booking_hint:
                    booking_hint = hint

            lower_url = resp.url.lower()
            if not result["contact_page"] and "contact" in lower_url:
                result["contact_page"] = resp.url
            if not result["about_page"] and "about" in lower_url:
                result["about_page"] = resp.url
            if not result["booking_page"] and any(k in lower_url for k in ["book", "appoint", "schedule", "reserv"]):
                result["booking_page"] = resp.url

            time.sleep(self.delay)

        result["emails"] = ";".join(sorted(all_emails))
        result["phone_found_on_site"] = phone_found
        result["has_contact_form"] = str(has_contact_form)
        result["has_booking"] = str(has_booking)
        result["booking_hint"] = booking_hint
        result["tech_stack"] = ";".join(sorted(tech_stack_found))
        result["crawl_status"] = "ok"

        for key, value in socials.items():
            result[key] = value

        return result


def clean_int(value) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def clean_float(value) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(str(value).strip())
    except Exception:
        return 0.0


def score_lead(row: pd.Series) -> int:
    score = 0

    website = str(row.get("website", "") or "").strip()
    emails = str(row.get("emails", "") or "").strip()
    has_contact_form = str(row.get("has_contact_form", "False")) == "True"
    has_booking = str(row.get("has_booking", "False")) == "True"
    status = str(row.get("business_status", "") or "").upper().strip()
    rating = clean_float(row.get("rating", 0))
    reviews = clean_int(row.get("review_count", 0))

    if status and status != "OPERATIONAL":
        score -= 100

    if website:
        score += 15
    else:
        score += 8

    if emails:
        score += 25

    if has_contact_form:
        score += 10

    if 4.0 <= rating <= 4.8:
        score += 15
    elif rating > 0:
        score += 8

    if 20 <= reviews <= 300:
        score += 15
    elif 5 <= reviews < 20:
        score += 8
    elif reviews > 300:
        score += 10

    if has_booking:
        score -= 5

    return score


def determine_pitch_angle(row: pd.Series) -> str:
    website = str(row.get("website", "") or "").strip()
    emails = str(row.get("emails", "") or "").strip()
    has_booking = str(row.get("has_booking", "False")) == "True"
    has_contact_form = str(row.get("has_contact_form", "False")) == "True"
    rating = clean_float(row.get("rating", 0))
    reviews = clean_int(row.get("review_count", 0))

    if not website:
        return "No website: pitch missed-call recovery + simple online presence"
    if website and not emails and not has_contact_form:
        return "Weak contact path: pitch AI receptionist + SMS lead capture"
    if website and not has_booking:
        return "No booking flow found: pitch AI booking + missed-call auto text"
    if has_booking and reviews < 20:
        return "Has booking but weak trust signals: pitch review automation + lead follow-up"
    if rating >= 4.5 and reviews >= 100:
        return "Strong business: pitch overflow call handling and after-hours conversion"
    return "General fit: pitch AI receptionist + lead capture"


def dedupe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()

    def norm_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    temp["_name_norm"] = temp["name"].apply(norm_text) if "name" in temp.columns else ""
    temp["_addr_norm"] = temp["address"].apply(norm_text) if "address" in temp.columns else ""
    temp["_phone_norm"] = temp["phone"].apply(norm_text) if "phone" in temp.columns else ""

    temp = temp.drop_duplicates(subset=["place_id"], keep="first") if "place_id" in temp.columns else temp
    temp = temp.drop_duplicates(subset=["_name_norm", "_addr_norm", "_phone_norm"], keep="first")

    temp = temp.drop(columns=["_name_norm", "_addr_norm", "_phone_norm"], errors="ignore")
    return temp


def enrich_one_row(enricher: SiteEnricher, row: pd.Series) -> Dict[str, str]:
    website = str(row.get("website", "") or "").strip()
    return enricher.analyze_site(website)


def enrich_dataframe(
    df: pd.DataFrame,
    timeout: int,
    max_pages: int,
    delay: float,
    max_workers: int,
) -> pd.DataFrame:
    enricher = SiteEnricher(
        timeout=timeout,
        max_pages=max_pages,
        delay=delay,
        max_workers=max_workers,
    )

    results: List[Optional[Dict[str, str]]] = [None] * len(df)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(enrich_one_row, enricher, df.iloc[idx]): idx
            for idx in range(len(df))
        }

        for count, future in enumerate(concurrent.futures.as_completed(future_to_index), start=1):
            idx = future_to_index[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = {
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
                    "crawl_status": "worker_error",
                }

            if count % 10 == 0:
                print(f"[INFO] Enriched {count}/{len(df)} websites...")

    enrich_df = pd.DataFrame(results)
    return pd.concat([df.reset_index(drop=True), enrich_df], axis=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich business websites from a Google Maps CSV.")
    parser.add_argument("--input", required=True, help="Input CSV from google_maps_lead_collector.py")
    parser.add_argument("--output", default="enriched_leads.csv", help="Output CSV file")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages per site")
    parser.add_argument("--delay", type=float, default=0.4, help="Delay between page fetches per site")
    parser.add_argument("--max-workers", type=int, default=5, help="Concurrent website workers")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.input)

    required_columns = {"name", "website"}
    missing = required_columns - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns in input CSV: {sorted(missing)}")

    print(f"[INFO] Loaded {len(df)} rows from {args.input}")
    df = dedupe_dataframe(df)
    print(f"[INFO] After dedupe: {len(df)} rows")

    enriched = enrich_dataframe(
        df=df,
        timeout=args.timeout,
        max_pages=args.max_pages,
        delay=args.delay,
        max_workers=args.max_workers,
    )

    enriched["lead_score"] = enriched.apply(score_lead, axis=1)
    enriched["pitch_angle"] = enriched.apply(determine_pitch_angle, axis=1)

    enriched = enriched.sort_values(
        by=["lead_score", "review_count", "rating"],
        ascending=[False, False, False],
        na_position="last"
    )

    enriched.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"[INFO] Saved enriched file to {args.output}")


if __name__ == "__main__":
    main()