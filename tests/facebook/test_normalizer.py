"""Tests for Facebook listing normalizers."""

from scrapers.facebook.normalizer import (
    listing_id_from_href,
    parse_location,
    parse_price,
    parse_title,
    parse_year,
    validate_listing_fields,
)


def test_listing_id_from_href():
    assert listing_id_from_href("https://www.facebook.com/marketplace/item/12345/?ref=search") == "12345"
    assert listing_id_from_href("https://example.com") is None


def test_parse_price_usd():
    amount, currency = parse_price(["2019 Camry", "$18,500", "Dallas, TX"])
    assert amount == 18500.0
    assert currency == "USD"


def test_parse_title_skips_price_line():
    assert parse_title(["2019 Toyota Camry", "$18,500", "Dallas, TX"]) == "2019 Toyota Camry"


def test_parse_location_from_tail():
    assert parse_location(["2019 Toyota Camry", "$18,500", "Dallas, TX"]) == "Dallas, TX"


def test_parse_year_from_title():
    assert parse_year("2019 Toyota Camry") == 2019
    assert parse_year("Toyota Camry") is None


def test_validate_listing_fields():
    assert not validate_listing_fields(
        listing_id="1",
        title="Car",
        listing_url="https://www.facebook.com/marketplace/item/1",
    )
    assert "missing listing_id" in validate_listing_fields(
        listing_id=None,
        title="Car",
        listing_url="https://www.facebook.com/marketplace/item/1",
    )
