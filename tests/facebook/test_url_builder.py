"""Tests for Facebook URL building."""

from services.city_resolver import ResolvedRegion
from scrapers.facebook.url_builder import build_search_url, build_vehicles_url


def _region() -> ResolvedRegion:
    return ResolvedRegion(
        raw_input="Dallas, TX",
        display_name="Dallas, TX",
        city="Dallas",
        state="TX",
        country="US",
        radius_km=80.0,
        craigslist_subdomain="dallas",
        craigslist_area_name="dallas",
        craigslist_base_url="https://dallas.craigslist.org",
        facebook_query="Dallas, TX",
        facebook_slug="dallas",
    )


def test_build_vehicles_url_uses_city_slug_path():
    url = build_vehicles_url(_region())
    assert "/marketplace/dallas/vehicles" in url
    assert "sortBy=creation_time_descend" in url
    assert "radius=" in url


def test_build_search_url_matches_vehicles_url():
    assert build_search_url(_region()) == build_vehicles_url(_region())
