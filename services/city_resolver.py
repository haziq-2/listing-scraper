"""Resolve a free-text region into source-specific search targets.

Accepts any region string — city, metro, state, or country — and produces:

* Craigslist: the best-matching regional subdomain from the official worldwide
  site list (cached locally).
* Facebook: latitude/longitude + radius via OpenStreetMap geocoding.
"""

from __future__ import annotations

import re
import unicodedata

from loguru import logger
from pydantic import BaseModel

from config import get_settings
from services.craigslist_sites import CraigslistSite, CraigslistSiteIndex
from services.facebook_locations import FacebookLocationResolver
from services.geocoder import Geocoder

_STATE_SUFFIX = re.compile(r",\s*([A-Za-z]{2,3})\.?\s*$")


class ResolvedRegion(BaseModel):
    """Source-specific search targets derived from a user region string."""

    raw_input: str
    display_name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float = 80.0

    craigslist_subdomain: str
    craigslist_area_name: str
    craigslist_base_url: str
    facebook_query: str
    facebook_slug: str
    facebook_location_tokens: list[str] = []

    # Backward-compatible aliases used elsewhere in the codebase.
    @property
    def facebook_location(self) -> str:
        return self.display_name


# Backward compatibility: older code imports ResolvedCity.
ResolvedCity = ResolvedRegion


class RegionResolver:
    """Turns user region text into per-source search targets."""

    def __init__(self) -> None:
        self._sites = CraigslistSiteIndex()
        self._geocoder = Geocoder()
        self._facebook = FacebookLocationResolver()
        self._settings = get_settings()

    def resolve(self, raw_input: str, radius_km: float | None = None) -> ResolvedRegion:
        text = re.sub(r"\s+", " ", (raw_input or "")).strip()
        if not text:
            raise ValueError("Region input cannot be empty")

        radius = radius_km if radius_km is not None else self._settings.search_radius_km
        geocoded = self._geocoder.geocode(text)

        city, state = self._parse_local_parts(text, geocoded)
        display_name = geocoded.display_name if geocoded else text
        country = geocoded.country if geocoded else None
        latitude = geocoded.latitude if geocoded else None
        longitude = geocoded.longitude if geocoded else None

        site = self._match_craigslist(text, geocoded)
        if site is None:
            subdomain = self._slugify(city or text)
            area_name = city or text
            logger.warning(
                "No Craigslist site match for '{}'; falling back to subdomain '{}'",
                text,
                subdomain,
            )
        else:
            subdomain = site.subdomain
            area_name = site.name

        fb_slug = self._facebook.resolve_slug(city=city, raw_input=text)
        fb_tokens = sorted(
            self._facebook.region_location_tokens(
                raw_input=text,
                city=city,
                state=state,
                country=country,
            )
        )

        resolved = ResolvedRegion(
            raw_input=text,
            display_name=display_name,
            city=city,
            state=state,
            country=country,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius,
            craigslist_subdomain=subdomain,
            craigslist_area_name=area_name,
            craigslist_base_url=f"https://{subdomain}.craigslist.org",
            facebook_query=text,
            facebook_slug=fb_slug,
            facebook_location_tokens=fb_tokens,
        )
        logger.info(
            "Resolved region '{}' -> craigslist={} ({}) | facebook_slug={} | coords=({}, {}) radius={}km",
            text,
            resolved.craigslist_base_url,
            resolved.craigslist_area_name,
            resolved.facebook_slug,
            f"{latitude:.4f}" if latitude is not None else "n/a",
            f"{longitude:.4f}" if longitude is not None else "n/a",
            radius,
        )
        return resolved

    def _match_craigslist(self, text: str, geocoded) -> CraigslistSite | None:
        queries: list[str] = [text]
        if geocoded:
            if geocoded.city:
                queries.append(geocoded.city)
            if geocoded.state:
                queries.append(f"{geocoded.city}, {geocoded.state}" if geocoded.city else geocoded.state)
            if geocoded.country:
                queries.append(f"{geocoded.city}, {geocoded.country}" if geocoded.city else geocoded.country)
        return self._sites.match(
            *queries,
            country=geocoded.country if geocoded else None,
            country_code=geocoded.country_code if geocoded else None,
        )

    @staticmethod
    def _parse_local_parts(text: str, geocoded) -> tuple[str | None, str | None]:
        if geocoded and geocoded.city:
            return geocoded.city, geocoded.state

        state: str | None = None
        city = text
        match = _STATE_SUFFIX.search(text)
        if match:
            state = match.group(1).upper()
            city = _STATE_SUFFIX.sub("", text).strip()
        return city or None, state

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


# Backward compatibility: older code imports CityResolver.
CityResolver = RegionResolver
