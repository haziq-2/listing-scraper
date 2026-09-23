"""Craigslist worldwide site index.

Fetches and caches the official site list from craigslist.org/about/sites so any
region string can be matched to the correct subdomain (US, Canada, Europe, etc.).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger

from config import get_settings

_SITES_URL = "https://www.craigslist.org/about/sites"
# Current site list: https://www.craigslist.org/area/{slug}
_AREA_RE = re.compile(r"https?://(?:www\.)?craigslist\.org/area/([a-z0-9-]+)/?", re.I)
# Legacy list: https://{slug}.craigslist.org
_SUBDOMAIN_RE = re.compile(r"https?://([a-z0-9-]+)\.craigslist\.org/?", re.I)
_MIN_CACHED_SITES = 50


@dataclass(frozen=True)
class CraigslistSite:
    subdomain: str
    name: str
    url: str
    section: str | None = None
    subsection: str | None = None


def _normalize(text: str) -> str:
    lowered = text.lower().strip()
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _token_set(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if t}


def _area_slug(href: str) -> str | None:
    area = _AREA_RE.match(href)
    if area:
        return area.group(1).lower()
    legacy = _SUBDOMAIN_RE.match(href)
    if not legacy:
        return None
    slug = legacy.group(1).lower()
    if slug in {"www", "web"}:
        return None
    return slug


def parse_sites_html(html: str) -> list[CraigslistSite]:
    """Parse the Craigslist worldwide sites page into regional sites."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    sites: list[CraigslistSite] = []
    current_section: str | None = None
    current_subsection: str | None = None

    for element in soup.select("h1, h2, h3, h4, a[href]"):
        if element.name in {"h1", "h2"}:
            current_section = element.get_text(strip=True) or None
            current_subsection = None
            continue
        if element.name in {"h3", "h4"}:
            current_subsection = element.get_text(strip=True) or None
            continue

        href = element.get("href", "")
        slug = _area_slug(href)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        name = element.get_text(strip=True) or slug
        sites.append(
            CraigslistSite(
                subdomain=slug,
                name=name,
                url=f"https://www.craigslist.org/area/{slug}",
                section=current_section,
                subsection=current_subsection,
            )
        )
    return sites


class CraigslistSiteIndex:
    """Searchable index of every Craigslist regional site."""

    def __init__(self, cache_path: Path | None = None) -> None:
        settings = get_settings()
        self.cache_path = cache_path or settings.craigslist_sites_cache_path
        self.cache_ttl = timedelta(hours=settings.craigslist_sites_cache_ttl_hours)
        self._sites: list[CraigslistSite] | None = None

    def sites(self) -> list[CraigslistSite]:
        if self._sites is None:
            self._sites = self._load()
        return self._sites

    def match(self, *queries: str, country: str | None = None, country_code: str | None = None) -> CraigslistSite | None:
        """Return the best-matching Craigslist site for one or more query strings."""
        candidates = [q for q in queries if q and q.strip()]
        if not candidates:
            return None

        best: CraigslistSite | None = None
        best_score = 0
        for site in self.sites():
            score = max(self._score(query, site) for query in candidates)
            score += self._country_bonus(site, country, country_code)
            if score > best_score:
                best_score = score
                best = site

        if best and best_score >= 40:
            logger.debug(
                "Craigslist site match: '{}' -> {} ({}) score={}",
                candidates[0],
                best.subdomain,
                best.name,
                best_score,
            )
            return best
        return None

    @staticmethod
    def _country_bonus(site: CraigslistSite, country: str | None, country_code: str | None) -> int:
        """Prefer sites in the geocoded country when names collide (e.g. London UK vs ON)."""
        code = (country_code or "").upper()
        country_norm = (country or "").lower()
        section = (site.section or "").lower()
        subsection = (site.subsection or "").lower()

        if code == "US" or "united states" in country_norm:
            return 30 if section == "us" else 0
        if code == "CA" or country_norm == "canada":
            return 30 if section == "canada" else 0
        if code == "GB" or "united kingdom" in country_norm or country_norm == "uk":
            return 30 if "united kingdom" in subsection else 0
        if code == "AU" or country_norm == "australia":
            return 30 if section == "oceania" else 0
        if code == "DE" or country_norm == "germany" or "deutschland" in country_norm:
            return 30 if "germany" in subsection else 0
        return 0

    @staticmethod
    def _score(query: str, site: CraigslistSite) -> int:
        q = _normalize(query)
        name = _normalize(site.name)
        sub = _normalize(site.subdomain)

        if not q:
            return 0
        if q == name or q == sub:
            return 100
        if q in name or name in q:
            return 85
        if q in sub or sub in q:
            return 75

        q_tokens = _token_set(q)
        name_tokens = _token_set(name)
        if not q_tokens:
            return 0

        overlap = q_tokens & name_tokens
        if overlap:
            # Reward matching more of the query tokens (helps "San Francisco, CA").
            ratio = len(overlap) / len(q_tokens)
            return int(50 + ratio * 40)

        return 0

    def _load(self) -> list[CraigslistSite]:
        cached = self._read_cache()
        if cached is not None:
            return cached
        return self._fetch_and_cache()

    def _read_cache(self) -> list[CraigslistSite] | None:
        if not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            if datetime.now(timezone.utc) - fetched_at > self.cache_ttl:
                logger.debug("Craigslist site cache expired")
                return None
            sites = [
                CraigslistSite(
                    subdomain=row["subdomain"],
                    name=row["name"],
                    url=row["url"],
                    section=row.get("section"),
                    subsection=row.get("subsection"),
                )
                for row in payload["sites"]
            ]
            if len(sites) < _MIN_CACHED_SITES:
                logger.warning(
                    "Craigslist site cache only has {} site(s); refetching",
                    len(sites),
                )
                return None
            logger.debug("Loaded {} Craigslist sites from cache", len(sites))
            return sites
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read Craigslist site cache: {}", exc)
            return None

    def _fetch_and_cache(self) -> list[CraigslistSite]:
        logger.info("Fetching Craigslist worldwide site list...")
        time.sleep(1.0)  # polite pause before external request
        resp = requests.get(
            _SITES_URL,
            timeout=30,
            headers={"User-Agent": "AutoWatch/1.0 (vehicle listings monitor)"},
        )
        resp.raise_for_status()

        sites = parse_sites_html(resp.text)
        sites.sort(key=lambda s: s.name.lower())
        self._write_cache(sites)
        logger.info("Indexed {} Craigslist regional sites", len(sites))
        return sites

    def _write_cache(self, sites: list[CraigslistSite]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": _SITES_URL,
            "sites": [
                {
                    "subdomain": s.subdomain,
                    "name": s.name,
                    "url": s.url,
                    "section": s.section,
                    "subsection": s.subsection,
                }
                for s in sites
            ],
        }
        self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
