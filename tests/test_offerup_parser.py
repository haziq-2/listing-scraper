"""OfferUp feed parsing and search-parameter construction."""

from scrapers.offerup import (
    build_search_params,
    km_to_miles,
    listings_from_feed,
    page_cursor_from_feed,
    parse_mileage,
    parse_price,
)


def _feed() -> dict:
    return {
        "data": {
            "modularFeed": {
                "pageCursor": "cursor-2",
                "looseTiles": [
                    {
                        "__typename": "ModularFeedTileListing",
                        "listing": {
                            "listingId": "abc-123",
                            "title": "2018 Honda Civic EX",
                            "price": "$12,400",
                            "locationName": "Dallas, TX",
                            "vehicleMiles": "86,200",
                            "conditionText": "Good",
                            "image": {"url": "https://images.offerup.com/civic.jpg"},
                        },
                    },
                    {"__typename": "ModularFeedTileBanner", "title": "Sponsored"},
                ],
                "modules": [
                    {
                        "__typename": "ModularFeedModuleGrid",
                        "grid": {
                            "tiles": [
                                {
                                    "__typename": "ModularFeedTileListing",
                                    "listing": {
                                        "listingId": "def-456",
                                        "title": "2015 Toyota Camry",
                                        "price": 9800,
                                        "locationName": "Plano, TX",
                                        "vehicleMiles": 120000,
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
        }
    }


def test_listings_from_feed_skips_ads_and_parses_vehicles():
    listings = listings_from_feed(_feed(), fallback_location="Dallas")
    assert [item.listing_id for item in listings] == ["abc-123", "def-456"]

    civic = listings[0]
    assert civic.title == "2018 Honda Civic EX"
    assert civic.price == 12400
    assert civic.currency == "USD"
    assert civic.year == 2018
    assert civic.mileage == 86200
    assert civic.location == "Dallas, TX"
    assert civic.condition == "Good"
    assert civic.image_url == "https://images.offerup.com/civic.jpg"
    assert civic.listing_url == "https://offerup.com/item/detail/abc-123"
    assert civic.source_value == "offerup"

    camry = listings[1]
    assert camry.price == 9800
    assert camry.mileage == 120000
    assert camry.year == 2015


def test_page_cursor_and_duplicate_ids():
    payload = _feed()
    payload["data"]["modularFeed"]["modules"][0]["grid"]["tiles"].append(
        payload["data"]["modularFeed"]["looseTiles"][0]
    )
    listings = listings_from_feed(payload)
    assert [item.listing_id for item in listings] == ["abc-123", "def-456"]
    assert page_cursor_from_feed(payload) == "cursor-2"
    assert page_cursor_from_feed({}) is None


def test_search_params_include_location_category_and_query():
    params = build_search_params(
        latitude=32.7767,
        longitude=-96.797,
        radius_miles=km_to_miles(80),
        category_id="5.1",
        page_size=50,
        search_session_id="session-1",
        query="Honda Civic",
        page_cursor="cursor-2",
    )
    as_map = {item["key"]: item["value"] for item in params}
    assert as_map["cid"] == "5.1"
    assert as_map["lat"] == "32.77670"
    assert as_map["lon"] == "-96.79700"
    assert as_map["DISTANCE"] == "50"
    assert as_map["q"] == "Honda Civic"
    assert as_map["page_cursor"] == "cursor-2"
    assert as_map["limit"] == "50"


def test_price_and_mileage_helpers():
    assert parse_price("$1,250") == 1250
    assert parse_price(None) is None
    assert parse_mileage("12,345 mi") == 12345
    assert parse_mileage("") is None
