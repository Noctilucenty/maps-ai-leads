import os
import csv
import time
import argparse
from typing import Dict, List, Optional, Tuple, Set

import requests


API_BASE_NEARBY = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
API_BASE_TEXT = "https://maps.googleapis.com/maps/api/place/textsearch/json"
API_BASE_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"


class GoogleMapsLeadCollector:
    def __init__(self, api_key: str, delay_between_requests: float = 1.2) -> None:
        if not api_key:
            raise ValueError("Missing Google Maps API key.")
        self.api_key = api_key
        self.delay = max(delay_between_requests, 0.2)
        self.session = requests.Session()

    def _request(self, url: str, params: Dict) -> Dict:
        params = dict(params)
        params["key"] = self.api_key

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        status = data.get("status")

        if status in ("OK", "ZERO_RESULTS"):
            return data

        if status == "OVER_QUERY_LIMIT":
            raise RuntimeError("Google API quota exceeded or rate limit hit.")

        if status == "REQUEST_DENIED":
            raise RuntimeError(
                f"Google API request denied: {data.get('error_message', 'Unknown error')}"
            )

        if status == "INVALID_REQUEST":
            raise RuntimeError(f"Invalid request: {data}")

        raise RuntimeError(
            f"Google API error: {status} | {data.get('error_message', '')}"
        )

    def _fetch_next_page_with_retry(self, url: str, next_page_token: str) -> Optional[Dict]:
        for attempt in range(6):
            time.sleep(2.0)
            try:
                return self._request(url, {"pagetoken": next_page_token})
            except RuntimeError as exc:
                if "Invalid request" in str(exc):
                    print(f"[WARN] next_page_token not ready yet (attempt {attempt + 1}/6)...")
                    continue
                raise

        print("[WARN] Could not activate next_page_token; stopping pagination.")
        return None

    def text_search(
        self,
        query: str,
        region: Optional[str] = None,
        max_pages: int = 3
    ) -> List[Dict]:
        results: List[Dict] = []
        next_page_token: Optional[str] = None

        for page in range(max_pages):
            if next_page_token:
                data = self._fetch_next_page_with_retry(API_BASE_TEXT, next_page_token)
                if data is None:
                    break
            else:
                params = {"query": query}
                if region:
                    params["region"] = region
                data = self._request(API_BASE_TEXT, params)

            batch = data.get("results", [])
            results.extend(batch)

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
        max_pages: int = 3
    ) -> List[Dict]:
        results: List[Dict] = []
        next_page_token: Optional[str] = None

        for page in range(max_pages):
            if next_page_token:
                data = self._fetch_next_page_with_retry(API_BASE_NEARBY, next_page_token)
                if data is None:
                    break
            else:
                params = {
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
        fields = ",".join([
            "place_id",
            "name",
            "formatted_address",
            "formatted_phone_number",
            "international_phone_number",
            "website",
            "rating",
            "user_ratings_total",
            "types",
            "url",
            "geometry",
            "business_status"
        ])

        params = {
            "place_id": place_id,
            "fields": fields
        }

        data = self._request(API_BASE_DETAILS, params)
        return data.get("result", {})

    @staticmethod
    def _normalize_result(raw: Dict, details: Optional[Dict] = None) -> Dict:
        source = details if details else raw
        geometry = source.get("geometry", {}) or {}
        location = geometry.get("location", {}) or {}

        return {
            "place_id": source.get("place_id", raw.get("place_id", "")),
            "name": source.get("name", raw.get("name", "")),
            "address": source.get(
                "formatted_address",
                raw.get("formatted_address", raw.get("vicinity", ""))
            ),
            "phone": source.get("formatted_phone_number", ""),
            "international_phone": source.get("international_phone_number", ""),
            "website": source.get("website", ""),
            "rating": source.get("rating", raw.get("rating", "")),
            "review_count": source.get(
                "user_ratings_total",
                raw.get("user_ratings_total", "")
            ),
            "business_status": source.get("business_status", raw.get("business_status", "")),
            "types": "|".join(source.get("types", raw.get("types", []))),
            "latitude": location.get("lat", ""),
            "longitude": location.get("lng", ""),
            "google_maps_url": source.get("url", ""),
        }

    def enrich_places(
        self,
        places: List[Dict],
        include_details: bool = True
    ) -> List[Dict]:
        enriched: List[Dict] = []
        seen: Set[str] = set()

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
                    print(f"[WARN] Failed details for {place_id}: {exc}")

            normalized = self._normalize_result(place, details)
            enriched.append(normalized)

            if idx % 10 == 0:
                print(f"[INFO] Processed {idx} places...")

        return enriched

    @staticmethod
    def save_to_csv(rows: List[Dict], output_file: str) -> None:
        if not rows:
            print("[INFO] No rows to save.")
            return

        fieldnames = [
            "place_id",
            "name",
            "address",
            "phone",
            "international_phone",
            "website",
            "rating",
            "review_count",
            "business_status",
            "types",
            "latitude",
            "longitude",
            "google_maps_url",
        ]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"[INFO] Saved {len(rows)} rows to {output_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Google Maps Lead Collector using Google Places API"
    )
    parser.add_argument("--api-key", type=str, default=os.getenv("GOOGLE_MAPS_API_KEY"))
    parser.add_argument("--mode", choices=["text", "nearby"], required=True)

    parser.add_argument("--query", type=str, help="Example: 'auto repair shops in San Jose, CA'")
    parser.add_argument("--region", type=str, help="Optional ccTLD region code, e.g. us")

    parser.add_argument("--lat", type=float, help="Latitude for nearby mode")
    parser.add_argument("--lng", type=float, help="Longitude for nearby mode")
    parser.add_argument("--radius", type=int, default=5000, help="Radius in meters for nearby mode")
    parser.add_argument("--keyword", type=str, help="Keyword for nearby mode, e.g. 'dentist'")
    parser.add_argument("--business-type", type=str, help="Google business type, e.g. restaurant")

    parser.add_argument("--max-pages", type=int, default=3, help="Max pagination pages")
    parser.add_argument("--no-details", action="store_true", help="Skip place details requests")
    parser.add_argument("--output", type=str, default="google_maps_leads.csv")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Set GOOGLE_MAPS_API_KEY or pass --api-key.")

    collector = GoogleMapsLeadCollector(api_key=args.api_key)

    if args.mode == "text":
        if not args.query:
            raise SystemExit("--query is required in text mode.")
        print(f"[INFO] Running text search: {args.query}")
        raw_places = collector.text_search(
            query=args.query,
            region=args.region,
            max_pages=args.max_pages
        )
    else:
        if args.lat is None or args.lng is None:
            raise SystemExit("--lat and --lng are required in nearby mode.")
        print(f"[INFO] Running nearby search at {args.lat},{args.lng}")
        raw_places = collector.nearby_search(
            location=(args.lat, args.lng),
            radius=args.radius,
            keyword=args.keyword,
            business_type=args.business_type,
            max_pages=args.max_pages
        )

    print(f"[INFO] Found {len(raw_places)} raw places")

    rows = collector.enrich_places(
        places=raw_places,
        include_details=not args.no_details
    )

    collector.save_to_csv(rows, args.output)


if __name__ == "__main__":
    main()