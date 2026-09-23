"""Facebook region token matching, including metro suburbs."""

from services.facebook_locations import FacebookLocationResolver


def test_dallas_search_keeps_dfw_suburbs():
    tokens = FacebookLocationResolver.region_location_tokens(
        raw_input="Dallas, TX",
        city="Dallas",
        state="Texas",
        country="United States",
    )
    assert "dallas" in tokens
    assert "plano" in tokens
    assert "fort worth" in tokens
    assert "euless" in tokens
    assert FacebookLocationResolver.listing_matches_region("Plano, TX", tokens)
    assert FacebookLocationResolver.listing_matches_region("Euless", tokens)
    assert not FacebookLocationResolver.listing_matches_region("Seattle, WA", tokens)


def test_suburb_search_still_includes_dallas():
    tokens = FacebookLocationResolver.region_location_tokens(
        raw_input="Plano, TX",
        city="Plano",
        state="Texas",
        country="United States",
    )
    assert "dallas" in tokens
    assert FacebookLocationResolver.listing_matches_region("Dallas, TX", tokens)
