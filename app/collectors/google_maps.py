"""
Google Maps / Google Places API lead collector.
Refactored core class — CLI lives in scripts/collect_leads.py and scripts/batch_collect.py.
"""
import time
from typing import Dict, List, Optional, Set, Tuple

import requests

from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

API_BASE_NEARBY = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
API_BASE_TEXT = "https://maps.googleapis.com/maps/api/place/textsearch/json"
API_BASE_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

DETAIL_FIELDS = ",".join([
    "place_id", "name", "formatted_address", "formatted_phone_number",
    "international_phone_number", "website", "rating", "user_ratings_total",
    "types", "url", "geometry", "business_status",
])


class GoogleMapsLeadCollector:
    def __init__(self, api_key: str, delay_between_requests: float = 1.2) -> None:
        if not api_key:
            raise ValueError(
                "Missing Google Maps API key. "
                "Set GOOGLE_MAPS_API_KEY in your .env file."
            )
        self.api_key = api_key
        self.delay = max(delay_between_requests, 0.2)
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _request(self, url: str, params: Dict) -> Dict:
        params = dict(params)
        params["key"] = self.api_key

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("Google API request timed out.")
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"Could not connect to Google API: {exc}")
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(f"Google API HTTP error: {exc}")

        data = resp.json()
        status = data.get("status")

        if status in ("OK", "ZERO_RESULTS"):
            return data
        if status == "OVER_QUERY_LIMIT":
            raise RuntimeError("Google API quota exceeded. Wait and try again.")
        if status == "REQUEST_DENIED":
            raise RuntimeError(
                f"Google API key denied: "
                f"{data.get('error_message', 'Check your key and enabled APIs.')}"
            )
        if status == "INVALID_REQUEST":
            raise RuntimeError(f"Invalid Google API request: {data}")

        raise RuntimeError(
            f"Google API error [{status}]: {data.get('error_message', '')}"
        )

    def _next_page(self, url: str, token: str) -> Optional[Dict]:
        """Fetch the next page, retrying until the token becomes valid."""
        for attempt in range(6):
            time.sleep(2.0)
            try:
                return self._request(url, {"pagetoken": token})
            except RuntimeError as exc:
                if "Invalid" in str(exc):
                    logger.warning(f"next_page_token not ready (attempt {attempt + 1}/6)…")
                    continue
                raise
        logger.warning("Could not activate next_page_token; stopping pagination.")
        return None

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def text_search(
        self,
        query: str,
        region: Optional[str] = None,
        max_pages: int = 3,
    ) -> List[Dict]:
        results: List[Dict] = []
        next_page_token: Optional[str] = None

        for page in range(max_pages):
            if next_page_token:
                data = self._next_page(API_BASE_TEXT, next_page_token)
                if data is None:
                    break
            else:
                params: Dict = {"query": query}
                if region:
                    params["region"] = region
                data = self._request(API_BASE_TEXT, params)

            batch = data.get("results", [])
            results.extend(batch)
            logger.debug(f"  page {page + 1}: +{len(batch)} (total {len(results)})")

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break

            time.sleep(self.delay)

        return results

    def nearby_search(
        self,
        location: Tuple[float, float],
        radius: int,
        keyword: Optional[str] = None,
        business_type: Optional[str] = None,
        max_pages: int = 3,
    ) -> List[Dict]:
        results: List[Dict] = []
        next_page_token: Optional[str] = None

        for page in range(max_pages):
            if next_page_token:
                data = self._next_page(API_BASE_NEARBY, next_page_token)
                if data is None:
                    break
            else:
                params: Dict = {
                    "location": f"{location[0]},{location[1]}",
                    "radius": radius,
                }
                if keyword:
                    params["keyword"] = keyword
                if business_type:
                    params["type"] = business_type
                data = self._request(API_BASE_NEARBY, params)

            batch = data.get("results", [])
            results.extend(batch)

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break

            time.sleep(self.delay)

        return results

    def place_details(self, place_id: str) -> Dict:
        data = self._request(
            API_BASE_DETAILS,
            {"place_id": place_id, "fields": DETAIL_FIELDS},
        )
        return data.get("result", {})

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(raw: Dict, details: Optional[Dict] = None) -> Dict:
        src = details if details else raw
        geo = (src.get("geometry") or {})
        loc = geo.get("location") or {}

        return {
            "place_id": src.get("place_id", raw.get("place_id", "")),
            "name": src.get("name", raw.get("name", "")),
            "address": src.get(
                "formatted_address",
                raw.get("formatted_address", raw.get("vicinity", "")),
            ),
            "phone": src.get("formatted_phone_number", ""),
            "international_phone": src.get("international_phone_number", ""),
            "website": src.get("website", ""),
            "rating": src.get("rating", raw.get("rating", "")),
            "review_count": src.get(
                "user_ratings_total", raw.get("user_ratings_total", "")
            ),
            "business_status": src.get(
                "business_status", raw.get("business_status", "")
            ),
            "types": "|".join(src.get("types", raw.get("types", []))),
            "latitude": loc.get("lat", ""),
            "longitude": loc.get("lng", ""),
            "google_maps_url": src.get("url", ""),
        }

    # ------------------------------------------------------------------
    # Batch enrichment
    # ------------------------------------------------------------------

    def enrich_places(
        self,
        places: List[Dict],
        include_details: bool = True,
        extra_fields: Optional[Dict] = None,
    ) -> List[Dict]:
        """Fetch place details for each result and normalize into flat dicts."""
        enriched: List[Dict] = []
        seen: Set[str] = set()
        extra_fields = extra_fields or {}

        for idx, place in enumerate(places, start=1):
            place_id = place.get("place_id")
            if not place_id or place_id in seen:
                continue
            seen.add(place_id)

            details = None
            if include_details:
                try:
                    details = self.place_details(place_id)
                    time.sleep(self.delay)
                except Exception as exc:
                    logger.warning(f"Details failed for {place_id}: {exc}")

            row = self._normalize(place, details)
            row.update(extra_fields)
            enriched.append(row)

            if idx % 10 == 0:
                logger.info(f"  processed {idx}/{len(places)} places…")

        return enriched

    # ------------------------------------------------------------------
    # CSV output (kept for backward compat with root-level script)
    # ------------------------------------------------------------------

    @staticmethod
    def save_to_csv(rows: List[Dict], output_file: str) -> None:
        import csv

        if not rows:
            logger.info("No rows to save.")
            return

        fieldnames = [
            "place_id", "name", "address", "phone", "international_phone",
            "website", "rating", "review_count", "business_status", "types",
            "latitude", "longitude", "google_maps_url",
        ]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Saved {len(rows)} rows → {output_file}")
