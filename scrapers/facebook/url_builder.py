"""Build Facebook Marketplace search URLs."""

from __future__ import annotations

from urllib.parse import urlencode

from services.city_resolver import ResolvedRegion
from services.facebook_locations import km_to_facebook_radius_miles


def build_vehicles_url(region: ResolvedRegion) -> str:
    """City-scoped Vehicles browse feed. This page ignores a ``query`` parameter."""
    slug = region.facebook_slug
    radius_mi = km_to_facebook_radius_miles(region.radius_km)
    params = {
        "sortBy": "creation_time_descend",
        "radius": str(radius_mi),
    }
    return f"https://www.facebook.com/marketplace/{slug}/vehicles?{urlencode(params)}"


def build_keyword_search_url(region: ResolvedRegion, query: str) -> str:
    """City-scoped Marketplace search. ``/vehicles`` does not honor ``query``."""
    slug = region.facebook_slug
    radius_mi = km_to_facebook_radius_miles(region.radius_km)
    params = {
        "query": query.strip(),
        "sortBy": "creation_time_descend",
        "radius": str(radius_mi),
    }
    return f"https://www.facebook.com/marketplace/{slug}/search/?{urlencode(params)}"


def build_search_url(region: ResolvedRegion, query: str | None = None) -> str:
    """Vehicles browse URL, or a keyword search URL when ``query`` is set."""
    text = (query or "").strip()
    if text:
        return build_keyword_search_url(region, text)
    return build_vehicles_url(region)
