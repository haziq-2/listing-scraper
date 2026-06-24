"""Console notifier for newly discovered vehicles."""

from __future__ import annotations

from typing import Iterable

from loguru import logger

from models import VehicleListing
from services.deduplicator import ScanStats

_DIVIDER = "-" * 48


class ConsoleNotifier:
    """Prints clean, human-readable cards for new listings."""

    def notify_many(
        self,
        listings: Iterable[VehicleListing],
        *,
        stats: ScanStats | None = None,
        db_total: int | None = None,
    ) -> int:
        listings = list(listings)
        if not listings:
            logger.info("No new vehicles this cycle.")
            self._print_empty_summary(stats, db_total)
            return 0

        for listing in listings:
            self.notify(listing)
        print(f"\n{len(listings)} new vehicle(s) reported.\n")
        return len(listings)

    @staticmethod
    def _print_empty_summary(stats: ScanStats | None, db_total: int | None) -> None:
        lines = ["", _DIVIDER, "No new vehicles found.", _DIVIDER]
        if stats and stats.scraped > 0:
            lines.append(
                f"Scanned {stats.scraped} listing(s); all were already known "
                f"({stats.already_known} matched your database)."
            )
            if stats.filtered_out:
                lines.append(f"{stats.filtered_out} new listing(s) were hidden by your filters.")
            if db_total is not None:
                lines.append(f"Database total: {db_total} listing(s) tracked.")
            lines.append(
                "AutoWatch only shows newly posted vehicles. "
                "Delete data/vehicles.db to re-report everything as new."
            )
        lines.append(_DIVIDER)
        print("\n".join(lines))

    @staticmethod
    def notify(listing: VehicleListing) -> None:
        source_label = listing.source.label if hasattr(listing.source, "label") else str(listing.source)
        lines = [
            "",
            _DIVIDER,
            "NEW VEHICLE FOUND",
            _DIVIDER,
            f"Source:   {source_label}",
            f"Title:    {listing.title}",
            f"Price:    {listing.price_display}",
            f"Location: {listing.location or 'N/A'}",
            f"URL:      {listing.listing_url}",
            _DIVIDER,
        ]
        print("\n".join(lines))

    def print_inventory(
        self,
        rows: list,
        *,
        total: int,
        showing: int,
    ) -> None:
        """Print all stored vehicles from the database."""
        if not rows:
            print(f"\n{_DIVIDER}\nNo vehicles in database.\n{_DIVIDER}\n")
            return

        print(f"\n{_DIVIDER}")
        print(f"STORED VEHICLES ({showing} of {total})")
        print(_DIVIDER)

        for index, row in enumerate(rows, start=1):
            source = str(row["source"]).capitalize()
            price = row["price"]
            price_text = f"${price:,.0f}" if price is not None else "N/A"
            location = row["location"] or "N/A"
            first_seen = (row["first_seen"] or "")[:19].replace("T", " ")

            print(f"\n{index}. [{source}] {row['title']}")
            print(f"   Price:    {price_text}")
            print(f"   Location: {location}")
            print(f"   First seen: {first_seen}")
            print(f"   URL:      {row['listing_url']}")

        print(f"\n{_DIVIDER}")
        print(f"Showing {showing} of {total} vehicle(s).\n")
