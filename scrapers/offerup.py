"""OfferUp vehicle scraper.

OfferUp's public site loads cars & trucks (category ``5.1``) from
``POST https://offerup.com/api/graphql`` (operation ``GetModularFeed``).
The search is centered on latitude/longitude. OfferUp only serves this feed
inside the United States; other locations get a geolocation block page.

Anti-blocking matches the Craigslist scraper: one user agent per run, pauses
between pages, and retries. A block or CAPTCHA stops the source.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import requests
from loguru import logger

from config import Settings, get_settings
from models import Source, VehicleListing
from services.city_resolver import ResolvedRegion
from utils import human_delay, looks_like_captcha, random_user_agent, with_retries

_GRAPHQL_URL = "https://offerup.com/api/graphql"
_ITEM_URL = "https://offerup.com/item/detail/{listing_id}"
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_MILES_PER_KM = 0.621371

# Only the listing fields this app stores. Ads and other tile types are ignored.
_QUERY = """
query GetModularFeed($searchParams: [SearchParam]) {
  modularFeed(params: $searchParams) {
    pageCursor
    looseTiles {
      __typename
      ... on ModularFeedTileListing {
        listing { ...offerupListing }
      }
    }
    modules {
      __typename
      ... on ModularFeedModuleGrid {
        grid {
          tiles {
            __typename
            ... on ModularFeedTileListing {
              listing { ...offerupListing }
            }
          }
        }
      }
    }
  }
}

fragment offerupListing on ModularFeedListing {
  listingId
  title
  price
  locationName
  vehicleMiles
  conditionText
  image { url }
}
"""


def km_to_miles(radius_km: float) -> int:
    """OfferUp's DISTANCE param is miles. Keep a small floor so a search still runs."""
    return max(5, int(round(radius_km * _MILES_PER_KM)))


def build_search_params(
    *,
    latitude: float,
    longitude: float,
    radius_miles: int,
    category_id: str,
    page_size: int,
    search_session_id: str,
    query: str | None = None,
    page_cursor: str | None = None,
) -> list[dict[str, str]]:
    params = [
        {"key": "platform", "value": "web"},
        {"key": "lat", "value": f"{latitude:.5f}"},
        {"key": "lon", "value": f"{longitude:.5f}"},
        {"key": "DISTANCE", "value": str(radius_miles)},
        {"key": "cid", "value": category_id},
        {"key": "limit", "value": str(page_size)},
        {"key": "searchSessionId", "value": search_session_id},
    ]
    text = (query or "").strip()
    if text:
        params.append({"key": "q", "value": text})
    if page_cursor:
        params.append({"key": "page_cursor", "value": page_cursor})
    return params


def parse_price(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def parse_mileage(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def parse_year(title: str) -> int | None:
    match = _YEAR_RE.search(title or "")
    return int(match.group(1)) if match else None


def listings_from_feed(payload: dict[str, Any], *, fallback_location: str | None = None) -> list[VehicleListing]:
    """Turn one GetModularFeed response into vehicle listings. Ads are skipped."""
    feed = ((payload.get("data") or {}).get("modularFeed")) or {}
    tiles: list[dict[str, Any]] = []
    tiles.extend(tile for tile in (feed.get("looseTiles") or []) if isinstance(tile, dict))
    for module in feed.get("modules") or []:
        if not isinstance(module, dict):
            continue
        grid = module.get("grid") or {}
        tiles.extend(tile for tile in (grid.get("tiles") or []) if isinstance(tile, dict))
        tiles.extend(tile for tile in (module.get("tiles") or []) if isinstance(tile, dict))

    listings: list[VehicleListing] = []
    seen: set[str] = set()
    for tile in tiles:
        listing = _listing_from_tile(tile, fallback_location=fallback_location)
        if listing and listing.listing_id not in seen:
            seen.add(listing.listing_id)
            listings.append(listing)
    return listings


def page_cursor_from_feed(payload: dict[str, Any]) -> str | None:
    feed = ((payload.get("data") or {}).get("modularFeed")) or {}
    cursor = feed.get("pageCursor")
    if cursor is None:
        return None
    text = str(cursor).strip()
    return text or None


def _listing_from_tile(tile: dict[str, Any], *, fallback_location: str | None) -> VehicleListing | None:
    raw = tile.get("listing")
    if not isinstance(raw, dict):
        return None
    listing_id = str(raw.get("listingId") or "").strip()
    title = str(raw.get("title") or "").strip()
    if not listing_id or not title:
        return None
    image = raw.get("image") or {}
    image_url = image.get("url") if isinstance(image, dict) else None
    return VehicleListing(
        source=Source.OFFERUP,
        listing_id=listing_id,
        title=title,
        listing_url=_ITEM_URL.format(listing_id=listing_id),
        price=parse_price(raw.get("price")),
        currency="USD",
        year=parse_year(title),
        mileage=parse_mileage(raw.get("vehicleMiles")),
        location=(str(raw.get("locationName")).strip() if raw.get("locationName") else None) or fallback_location,
        condition=(str(raw.get("conditionText")).strip() if raw.get("conditionText") else None),
        image_url=str(image_url).strip() if image_url else None,
        raw_payload=json.dumps(raw, separators=(",", ":")),
    )


class OfferUpScraper:
    """Scrapes OfferUp cars & trucks around a resolved region's coordinates."""

    source = Source.OFFERUP

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = requests.Session()
        self._user_agent = random_user_agent()
        self.session.headers.update(
            {
                "User-Agent": self._user_agent,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "Origin": "https://offerup.com",
                "Referer": "https://offerup.com/search",
            }
        )

    def scrape(self, region: ResolvedRegion, query: str | None = None) -> list[VehicleListing]:
        if region.latitude is None or region.longitude is None:
            logger.warning("OfferUp needs coordinates for '{}'; skipping.", region.display_name)
            return []

        radius_miles = km_to_miles(region.radius_km)
        session_id = str(uuid.uuid4())
        logger.info(
            "OfferUp scraping cars & trucks near {} ({:.4f}, {:.4f}) within {} mi",
            region.display_name,
            region.latitude,
            region.longitude,
            radius_miles,
        )

        results: dict[str, VehicleListing] = {}
        cursor: str | None = None
        while len(results) < self.settings.offerup_max_listings:
            params = build_search_params(
                latitude=region.latitude,
                longitude=region.longitude,
                radius_miles=radius_miles,
                category_id=self.settings.offerup_category_id,
                page_size=self.settings.offerup_page_size,
                search_session_id=session_id,
                query=query,
                page_cursor=cursor,
            )
            try:
                payload = self._fetch(params)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to fetch OfferUp feed: {}", exc)
                break

            if payload is None:
                break

            for listing in listings_from_feed(payload, fallback_location=region.city or region.display_name):
                results.setdefault(listing.listing_id, listing)
                if len(results) >= self.settings.offerup_max_listings:
                    break

            next_cursor = page_cursor_from_feed(payload)
            if not next_cursor or next_cursor == cursor or len(results) >= self.settings.offerup_max_listings:
                break
            cursor = next_cursor
            human_delay(self.settings.offerup_min_delay, self.settings.offerup_max_delay)

        listings = list(results.values())[: self.settings.offerup_max_listings]
        logger.info("OfferUp produced {} listing(s)", len(listings))
        return listings

    @with_retries
    def _fetch(self, search_params: list[dict[str, str]]) -> dict[str, Any] | None:
        response = self.session.post(
            _GRAPHQL_URL,
            json={
                "operationName": "GetModularFeed",
                "variables": {"searchParams": search_params},
                "query": _QUERY,
            },
            timeout=self.settings.offerup_request_timeout,
        )
        if _is_geo_block(response):
            logger.error(
                "OfferUp refused the request (geolocation unavailable). "
                "This source only works from the United States."
            )
            return None
        if response.status_code >= 400 or looks_like_captcha(response.text):
            logger.warning("OfferUp blocked the feed (HTTP {}). Pausing this source.", response.status_code)
            return None
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            logger.warning("OfferUp feed returned errors: {}", errors[0].get("message", errors[0]))
            if not (payload.get("data") or {}).get("modularFeed"):
                return None
        return payload


def _is_geo_block(response: requests.Response) -> bool:
    if response.status_code not in {403, 451}:
        return False
    text = response.text.lower()
    return "geolocation unavailable" in text or "/unavailable/geo" in text
