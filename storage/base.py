"""Abstract vehicle repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from models import Source, VehicleListing


class VehicleRepository(ABC):
    """Data access layer for vehicle listings.

    Implementations: SQLite (default). PostgreSQL can be added by subclassing.
    """

    @abstractmethod
    def exists(self, source: Source | str, listing_id: str) -> bool:
        ...

    @abstractmethod
    def upsert(self, listing: VehicleListing) -> bool:
        """Return True when newly inserted."""

    @abstractmethod
    def upsert_many(self, listings: Iterable[VehicleListing]) -> tuple[set[str], int]:
        """Batch upsert. Returns (new_listing_ids, updated_count)."""

    @abstractmethod
    def known_listing_ids(self, source: Source | str) -> set[str]:
        """All listing IDs already stored for a source (for skip-before-scrape)."""

    @abstractmethod
    def count(self, source: str | None = None) -> int:
        ...

    @abstractmethod
    def close(self) -> None:
        ...
