"""New-listing detection and search-filter application.

The deduplicator is the heart of AutoWatch's "only show me new cars" promise.
It funnels every scraped listing through the database upsert and reports which
ones were genuinely new.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from loguru import logger

from database import Database
from models import VehicleListing


@dataclass(frozen=True)
class SearchFilters:
    """Optional user filters applied before a listing is shown."""

    make: str | None = None
    model: str | None = None
    max_price: float | None = None
    min_year: int | None = None

    def matches(self, listing: VehicleListing) -> bool:
        if self.make and (listing.make or "").lower() != self.make.lower():
            # Fall back to title match when structured make is missing.
            if not listing.make and self.make.lower() in listing.title.lower():
                pass
            else:
                return False
        if self.model:
            model_ok = (listing.model or "").lower() == self.model.lower()
            if not model_ok and self.model.lower() not in listing.title.lower():
                return False
        if self.max_price is not None and listing.price is not None and listing.price > self.max_price:
            return False
        if self.min_year is not None and listing.year is not None and listing.year < self.min_year:
            return False
        return True


@dataclass(frozen=True)
class ScanStats:
    """Counts from a single deduplication pass."""

    scraped: int
    already_known: int
    filtered_out: int
    new_count: int


class Deduplicator:
    """Persists listings and surfaces only newly-discovered ones."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def process(
        self,
        listings: Iterable[VehicleListing],
        filters: SearchFilters | None = None,
    ) -> tuple[list[VehicleListing], ScanStats]:
        """Upsert all listings; return the new ones that pass ``filters``."""
        listing_list = list(listings)
        scraped = len(listing_list)
        if not listing_list:
            stats = ScanStats(scraped=0, already_known=0, filtered_out=0, new_count=0)
            return [], stats

        new_ids, updated_count = self.db.upsert_many(listing_list)
        already_known = updated_count
        new_listings: list[VehicleListing] = []
        filtered_out = 0

        for listing in listing_list:
            if listing.listing_id not in new_ids:
                continue
            listing.is_new = True
            if filters and not filters.matches(listing):
                logger.debug("New listing filtered out: {}", listing.title)
                filtered_out += 1
                continue
            new_listings.append(listing)

        stats = ScanStats(
            scraped=scraped,
            already_known=already_known,
            filtered_out=filtered_out,
            new_count=len(new_listings),
        )
        logger.info(
            "Processed {} listing(s); {} already known; {} new after filters",
            stats.scraped,
            stats.already_known,
            stats.new_count,
        )
        return new_listings, stats
