"""Integration-style tests for Facebook card parsing."""

import json
from pathlib import Path

from scrapers.facebook.extractor import MarketplaceExtractor
from scrapers.facebook.metrics import ScrapeMetrics
from services.city_resolver import ResolvedRegion

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "facebook_sample_cards.json"


def _region() -> ResolvedRegion:
    return ResolvedRegion(
        raw_input="Dallas, TX",
        display_name="Dallas, TX",
        city="Dallas",
        state="TX",
        country="US",
        craigslist_subdomain="dallas",
        craigslist_area_name="dallas",
        craigslist_base_url="https://dallas.craigslist.org",
        facebook_query="Dallas, TX",
        facebook_slug="dallas",
        facebook_location_tokens=["dallas", "tx"],
    )


def test_parse_cards_from_fixture():
    cards = json.loads(FIXTURES.read_text(encoding="utf-8"))
    metrics = ScrapeMetrics()
    extractor = MarketplaceExtractor()
    listings = extractor.parse_cards(cards, _region(), metrics)

    assert len(listings) == 1
    assert metrics.extraction_failures == 1
    assert metrics.listings_skipped_location == 1
    titles = {l.title for l in listings}
    assert "2019 Toyota Camry" in titles
