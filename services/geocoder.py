"""Geocode free-text regions to coordinates via OpenStreetMap Nominatim.

Used to target Facebook Marketplace by latitude/longitude/radius so any region
worldwide can be searched without relying on a hardcoded city list.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from loguru import logger

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "AutoWatch/1.0 (vehicle listings monitor; contact: local-use)"


@dataclass(frozen=True)
class GeocodedRegion:
    """A region resolved to coordinates and structured place names."""

    query: str
    display_name: str
    latitude: float
    longitude: float
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None


class Geocoder:
    """Thin wrapper around the Nominatim search API (1 req/sec policy)."""

    def geocode(self, region: str) -> GeocodedRegion | None:
        region = (region or "").strip()
        if not region:
            return None

        # Nominatim usage policy: max 1 request per second.
        time.sleep(1.0)

        try:
            resp = requests.get(
                _NOMINATIM_URL,
                params={"q": region, "format": "jsonv2", "limit": 1, "addressdetails": 1},
                headers={"User-Agent": _USER_AGENT},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Geocoding failed for '{}': {}", region, exc)
            return None

        if not results:
            logger.warning("No geocoding results for '{}'", region)
            return None

        hit = results[0]
        address = hit.get("address") or {}
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
        )
        state = address.get("state") or address.get("region")
        country = address.get("country")
        country_code = (address.get("country_code") or "").upper() or None

        result = GeocodedRegion(
            query=region,
            display_name=hit.get("display_name", region),
            latitude=float(hit["lat"]),
            longitude=float(hit["lon"]),
            city=city,
            state=state,
            country=country,
            country_code=country_code,
        )
        logger.info(
            "Geocoded '{}' -> {:.4f}, {:.4f} ({})",
            region,
            result.latitude,
            result.longitude,
            result.display_name,
        )
        return result
