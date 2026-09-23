"""Parse raw Facebook Marketplace card data into domain models."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from models import Source, VehicleListing
from scrapers.facebook.metrics import ScrapeMetrics
from scrapers.facebook.normalizer import (
    normalize_card_raw,
    parse_location,
    parse_price,
    parse_title,
    parse_year,
    validate_listing_fields,
    listing_id_from_href,
)
from scrapers.facebook.selectors import SELECTORS, primary
from services.city_resolver import ResolvedCity

# JavaScript run in the browser to extract card data from listing anchors.
_CARD_EXTRACTION_JS = """
(anchors) => {
    const seen = new Set();
    const cards = [];
    for (const a of anchors) {
        const match = a.href.match(/\\/marketplace\\/item\\/(\\d+)/);
        if (!match) continue;
        const listingId = match[1];
        if (seen.has(listingId)) continue;
        seen.add(listingId);
        const text = a.innerText || a.getAttribute("aria-label") || "";
        const lines = text.split("\\n").map(s => s.trim()).filter(Boolean);
        const img = a.querySelector("img");
        cards.push({
            listing_id: listingId,
            href: a.href,
            lines: lines,
            image: img ? img.src : null,
        });
    }
    return cards;
}
"""


class MarketplaceExtractor:
    """Extracts listing cards from a Playwright page and parses them."""

    def extract_cards_from_page(self, page) -> list[dict[str, Any]]:
        selector = primary(SELECTORS.listing_link)
        raw_cards: list[dict] = page.eval_on_selector_all(selector, _CARD_EXTRACTION_JS)
        return [c for c in raw_cards if listing_id_from_href(c.get("href", "")) or c.get("listing_id")]

    def parse_cards(
        self,
        cards: list[dict[str, Any]],
        region: ResolvedCity,
        metrics: ScrapeMetrics,
    ) -> list[VehicleListing]:
        # Keep every parsed card. Marketplace often labels a listing with a
        # nearby city even when it belongs in the searched feed.
        listings: dict[str, VehicleListing] = {}
        for card in cards:
            listing = self._parse_card(card, metrics)
            if not listing:
                continue
            metrics.listings_parsed += 1
            listings[listing.listing_id] = listing

        metrics.listings_kept = len(listings)
        logger.debug(
            "Kept {} Facebook card(s) for {} (other cities included)",
            metrics.listings_kept,
            region.raw_input,
        )
        return list(listings.values())

    def _parse_card(self, card: dict[str, Any], metrics: ScrapeMetrics) -> VehicleListing | None:
        listing_id = card.get("listing_id") or listing_id_from_href(card.get("href", ""))
        listing_url = f"https://www.facebook.com/marketplace/item/{listing_id}" if listing_id else ""
        lines: list[str] = card.get("lines", [])
        price, currency = parse_price(lines)
        title = parse_title(lines) or "Facebook Marketplace vehicle"
        location = parse_location(lines)
        year = parse_year(title)

        errors = validate_listing_fields(listing_id=listing_id, title=title, listing_url=listing_url)
        if errors:
            metrics.extraction_failures += 1
            logger.debug("Card validation failed {}: {}", errors, card)
            return None

        raw_payload = json.dumps(normalize_card_raw(card))
        listing = VehicleListing(
            source=Source.FACEBOOK,
            listing_id=str(listing_id),
            title=title,
            listing_url=listing_url,
            price=price,
            year=year,
            location=location,
            image_url=card.get("image"),
            currency=currency,
            raw_payload=raw_payload,
        )
        return listing
