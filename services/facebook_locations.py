"""Facebook Marketplace city slug resolution.

Facebook location-scopes search via a canonical city slug in the URL path:
``/marketplace/{slug}/search/`` — NOT via ``latitude``/``longitude`` query params
(those are ignored on the category path and fall back to account/IP location).
"""

from __future__ import annotations

import re
import unicodedata

from loguru import logger

# Metro slug when it differs from a simple slugified city name.
FACEBOOK_SLUG_OVERRIDES: dict[str, str] = {
    "new york": "nyc",
    "new york city": "nyc",
    "nyc": "nyc",
    "los angeles": "la",
    "la": "la",
    "san francisco": "sanfrancisco",
    "san francisco bay area": "sanfrancisco",
    "bay area": "sanfrancisco",
    "sf": "sanfrancisco",
    "washington": "dc",
    "washington dc": "dc",
    "washington d.c.": "dc",
    "dc": "dc",
    "fort worth": "dallas",
    "dfw": "dallas",
    "arlington": "dallas",
    "plano": "dallas",
    "frisco": "dallas",
    "mckinney": "dallas",
    "garland": "dallas",
    "irving": "dallas",
    "salt lake city": "saltlakecity",
    "slc": "saltlakecity",
    "las vegas": "lasvegas",
    "san antonio": "sanantonio",
    "san diego": "sandiego",
    "kansas city": "kansascity",
    "st louis": "stlouis",
    "saint louis": "stlouis",
    "oklahoma city": "oklahomacity",
    "okc": "oklahomacity",
    "minneapolis": "minneapolis",
    "twin cities": "minneapolis",
    "phoenix": "phoenix",
    "houston": "houston",
    "chicago": "chicago",
    "boston": "boston",
    "seattle": "seattle",
    "atlanta": "atlanta",
    "miami": "miami",
    "portland": "portland",
    "denver": "denver",
    "austin": "austin",
    "dallas": "dallas",
    "nashville": "nashville",
    "detroit": "detroit",
    "philadelphia": "philadelphia",
    "philly": "philadelphia",
}

# Allowed radius values (miles) for Facebook Marketplace URL param.
FB_RADIUS_MILES: tuple[int, ...] = (1, 2, 5, 10, 20, 40, 60, 80, 100, 250, 500)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def km_to_facebook_radius_miles(radius_km: float) -> int:
    """Pick the nearest Facebook-allowed radius (miles) for a km value."""
    miles = radius_km * 0.621371
    return min(FB_RADIUS_MILES, key=lambda x: abs(x - miles))


class FacebookLocationResolver:
    """Resolve a region string into a Facebook Marketplace city slug."""

    def resolve_slug(self, *, city: str | None, raw_input: str) -> str:
        for candidate in (raw_input, city or ""):
            key = candidate.strip().lower()
            if not key:
                continue
            # Try full input first (e.g. "Fort Worth, TX" -> fort worth part handled below).
            city_part = re.sub(r",\s*[A-Za-z]{2,3}\.?\s*$", "", key).strip()
            if city_part in FACEBOOK_SLUG_OVERRIDES:
                slug = FACEBOOK_SLUG_OVERRIDES[city_part]
                logger.debug("Facebook slug override: '{}' -> {}", candidate, slug)
                return slug
            slug = _slugify(city_part)
            if slug:
                logger.debug("Facebook slug from name: '{}' -> {}", candidate, slug)
                return slug

        slug = _slugify(raw_input)
        if not slug:
            raise ValueError(f"Could not derive Facebook city slug for '{raw_input}'")
        return slug

    @staticmethod
    def region_location_tokens(
        *,
        raw_input: str,
        city: str | None,
        state: str | None,
        country: str | None,
    ) -> set[str]:
        """City-level tokens used to filter listings to the target region."""
        tokens: set[str] = set()
        if city:
            tokens.add(city.strip().lower())

        input_city = re.sub(r",\s*[A-Za-z]{2,3}\.?\s*$", "", raw_input).strip().lower()
        if input_city:
            tokens.add(input_city)

        # Metro aliases: Fort Worth searches use the Dallas FB marketplace slug.
        if input_city in {"fort worth", "arlington", "plano", "frisco", "irving", "garland", "mckinney"}:
            tokens.update({"dallas", "fort worth", "arlington", "plano", "frisco", "irving", "garland", "mckinney"})

        return {t for t in tokens if len(t) >= 3}

    @staticmethod
    def listing_matches_region(location: str | None, tokens: set[str]) -> bool:
        """Return True when a listing's location string plausibly matches the region."""
        if not location or not tokens:
            return False
        loc = location.lower()
        return any(token in loc for token in tokens)
