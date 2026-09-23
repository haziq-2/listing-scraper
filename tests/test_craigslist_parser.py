"""Craigslist search-result parsing for current and legacy markup."""

from scrapers.craigslist import CraigslistScraper
from services.city_resolver import ResolvedRegion


def _city() -> ResolvedRegion:
    return ResolvedRegion(
        raw_input="Dallas, TX",
        display_name="Dallas, TX",
        city="Dallas",
        state="TX",
        craigslist_subdomain="dallas",
        craigslist_area_name="dallas",
        craigslist_base_url="https://dallas.craigslist.org",
        facebook_query="Dallas, TX",
        facebook_slug="dallas",
    )


def test_parse_opaque_view_urls():
    html = """
    <li class="cl-static-search-result" title="2018 Tesla Model 3">
      <a href="https://www.craigslist.org/view/d/euless-2018-tesla-model-long-range/qfZryvPUijbAD4ye6H3CMk">
        <div class="title">2018 Tesla Model 3 Long Range</div>
        <div class="details">
          <div class="price">$24,500</div>
          <div class="location">Euless</div>
        </div>
      </a>
    </li>
    """
    listings = CraigslistScraper()._parse_search(html, _city())
    assert len(listings) == 1
    listing = listings[0]
    assert listing.listing_id == "qfZryvPUijbAD4ye6H3CMk"
    assert listing.price == 24500
    assert listing.location == "Euless"
    assert listing.year == 2018


def test_parse_legacy_numeric_urls():
    html = """
    <li class="cl-static-search-result">
      <a href="https://dallas.craigslist.org/cto/d/dallas-2016-honda-civic/7890123456.html">
        <div class="title">2016 Honda Civic</div>
        <div class="price">$9,900</div>
      </a>
    </li>
    """
    listings = CraigslistScraper()._parse_search(html, _city())
    assert len(listings) == 1
    assert listings[0].listing_id == "7890123456"
    assert listings[0].price == 9900
