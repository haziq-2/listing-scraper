"""Build Facebook Marketplace search URLs."""

from __future__ import annotations

from services.city_resolver import ResolvedRegion
from services.facebook_locations import km_to_facebook_radius_miles


def build_vehicles_url(region: ResolvedRegion) -> str:
    """Direct city-scoped Vehicles category URL (preferred over search query params)."""
    slug = region.facebook_slug
    radius_mi = km_to_facebook_radius_miles(region.radius_km)
    return (
        f"https://www.facebook.com/marketplace/{slug}/vehicles"
        f"?sortBy=creation_time_descend&radius={radius_mi}"
    )


def build_search_url(region: ResolvedRegion) -> str:
    """Return the primary Marketplace vehicles URL for a region."""
    return build_vehicles_url(region)
