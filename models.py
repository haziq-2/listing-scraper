"""Pydantic data models shared across AutoWatch."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Source(str, Enum):
    """Supported listing sources."""

    CRAIGSLIST = "craigslist"
    FACEBOOK = "facebook"

    @property
    def label(self) -> str:
        return {"craigslist": "Craigslist", "facebook": "Facebook"}[self.value]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VehicleListing(BaseModel):
    """A normalized vehicle listing from any source.

    This is the canonical representation used by scrapers, the deduplicator and
    the database layer. ``source`` + ``listing_id`` form the natural key.
    """

    model_config = ConfigDict(use_enum_values=False)

    source: Source
    listing_id: str
    title: str
    listing_url: str

    price: float | None = None
    currency: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None
    location: str | None = None
    seller_name: str | None = None
    image_url: str | None = None
    posted_time: str | None = None

    # VIN / extra detail-page fields (Craigslist).
    vin: str | None = None
    condition: str | None = None
    fuel: str | None = None
    transmission: str | None = None

    # Raw card JSON from scraper for debugging / regression analysis.
    raw_payload: str | None = None

    # Lifecycle bookkeeping.
    first_seen: datetime = Field(default_factory=_utcnow)
    last_seen: datetime = Field(default_factory=_utcnow)
    is_new: bool = False

    @field_validator("listing_id", "title", "listing_url")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("required field cannot be empty")
        return value

    @field_validator("make", "model", "location", "seller_name", "posted_time", "vin", "condition", "fuel", "transmission")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @property
    def source_value(self) -> str:
        """Return the source as its raw string value regardless of enum/str."""
        return self.source.value if isinstance(self.source, Source) else str(self.source)

    @property
    def price_display(self) -> str:
        if self.price is None:
            return "N/A"
        return f"${self.price:,.0f}"
