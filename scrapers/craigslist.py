"""Craigslist vehicle scraper using requests + BeautifulSoup.

Scrapes the static search-result markup Craigslist serves to non-JS clients for
both "cars+trucks by owner" (``cto``) and "by dealer" (``ctd``), then optionally
visits each detail page to enrich the record (VIN, mileage, fuel, etc.).

Anti-blocking: rotating user agent, rate-limited sequential requests with
random delays, exponential backoff retries, and CAPTCHA detection.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from loguru import logger

from config import Settings, get_settings
from models import Source, VehicleListing
from services.city_resolver import ResolvedCity
from utils import human_delay, looks_like_captcha, random_user_agent, with_retries

# "cta" = all cars+trucks (owner + dealer in one page).
_SEARCH_PATHS: tuple[tuple[str, str], ...] = (
    ("cta", "all"),
)

_LEGACY_ID_RE = re.compile(r"/(\d+)\.html")
# Current listing URLs: /view/d/{slug}/{opaqueId}
_VIEW_ID_RE = re.compile(r"/view/d/[^/?#]+/([A-Za-z0-9_-]+)/?(?:[?#]|$)")
_PRICE_RE = re.compile(r"[\d,]+")
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


class CraigslistScraper:
    """Scrapes vehicle listings from a city's Craigslist site."""

    source = Source.CRAIGSLIST

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = requests.Session()
        self._user_agent = random_user_agent()
        self.session.headers.update(self._default_headers())

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }

    def scrape(self, city: ResolvedCity) -> list[VehicleListing]:
        """Return listings discovered for the resolved city (sequential)."""
        results: dict[str, VehicleListing] = {}
        for path, channel in _SEARCH_PATHS:
            url = (
                f"https://www.craigslist.org/search/area/{city.craigslist_subdomain}"
                f"?cat={path}&sort=date"
            )
            logger.info("Craigslist scraping {} listings: {}", channel, url)
            try:
                html = self._fetch(url)
            except Exception as exc:  # noqa: BLE001 - logged and skipped
                logger.error("Failed to fetch Craigslist {} page: {}", channel, exc)
                continue

            if looks_like_captcha(html):
                logger.warning("CAPTCHA / block detected on Craigslist search page. Pausing this source.")
                break

            for listing in self._parse_search(html, city):
                if listing.listing_id not in results:
                    results[listing.listing_id] = listing
                if len(results) >= self.settings.craigslist_max_listings:
                    break

            human_delay(self.settings.craigslist_min_delay, self.settings.craigslist_max_delay)
            if len(results) >= self.settings.craigslist_max_listings:
                break

        listings = list(results.values())[: self.settings.craigslist_max_listings]

        if self.settings.craigslist_fetch_details:
            self._enrich(listings)

        logger.info("Craigslist produced {} listing(s)", len(listings))
        return listings

    @with_retries
    def _fetch(self, url: str) -> str:
        resp = self.session.get(url, timeout=self.settings.craigslist_request_timeout)
        resp.raise_for_status()
        return resp.text

    def _parse_search(self, html: str, city: ResolvedCity) -> list[VehicleListing]:
        soup = BeautifulSoup(html, "html.parser")
        listings: list[VehicleListing] = []

        nodes = soup.select("li.cl-static-search-result")
        if not nodes:
            # Fallback for the JS gallery markup if it is ever returned.
            nodes = soup.select("li.cl-search-result")
        if not nodes:
            logger.warning(
                "Craigslist search page had no listing nodes ({} bytes). "
                "The results markup may have changed or the request was blocked.",
                len(html),
            )

        for node in nodes:
            try:
                listing = self._parse_node(node, city)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skipping unparseable Craigslist node: {}", exc)
                continue
            if listing:
                listings.append(listing)
        if nodes and not listings:
            logger.warning(
                "Craigslist found {} result node(s) but parsed 0 listings",
                len(nodes),
            )
        return listings

    def _parse_node(self, node, city: ResolvedCity) -> VehicleListing | None:
        anchor = node.find("a", href=True)
        if not anchor:
            return None
        url = anchor["href"].strip()
        if not url.startswith("http"):
            url = urljoin(city.craigslist_base_url, url)

        listing_id = self._listing_id(url, node)
        if not listing_id:
            return None

        title_el = node.select_one(".title") or anchor
        title = title_el.get_text(strip=True) or node.get("title") or "Untitled listing"

        price = self._parse_price(node.select_one(".price"))
        location_el = node.select_one(".location")
        location = location_el.get_text(strip=True) if location_el else city.city
        year = self._parse_year(title)

        return VehicleListing(
            source=self.source,
            listing_id=listing_id,
            title=title,
            listing_url=url,
            price=price,
            year=year,
            location=location,
        )

    def _enrich(self, listings: list[VehicleListing]) -> None:
        for listing in listings:
            human_delay(self.settings.craigslist_min_delay, self.settings.craigslist_max_delay)
            try:
                html = self._fetch(listing.listing_url)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not fetch detail page {}: {}", listing.listing_url, exc)
                continue
            if looks_like_captcha(html):
                logger.warning("CAPTCHA detected on Craigslist detail page. Stopping enrichment.")
                break
            self._apply_details(listing, html)

    def _apply_details(self, listing: VehicleListing, html: str) -> None:
        soup = BeautifulSoup(html, "html.parser")

        attrs = self._extract_attrs(soup)
        listing.vin = listing.vin or attrs.get("vin")
        listing.make = listing.make or attrs.get("make")
        listing.model = listing.model or attrs.get("model")
        listing.condition = listing.condition or attrs.get("condition")
        listing.fuel = listing.fuel or attrs.get("fuel")
        listing.transmission = listing.transmission or attrs.get("transmission")

        if attrs.get("year") and not listing.year:
            try:
                listing.year = int(attrs["year"])
            except ValueError:
                pass

        odometer = attrs.get("odometer")
        if odometer and listing.mileage is None:
            digits = re.sub(r"[^\d]", "", odometer)
            if digits:
                listing.mileage = int(digits)

        time_el = soup.select_one("time.date.timeago, time[datetime]")
        if time_el and time_el.has_attr("datetime"):
            listing.posted_time = time_el["datetime"]

        image = soup.select_one("img[src]")
        if image and not listing.image_url:
            listing.image_url = image.get("src")

    @staticmethod
    def _extract_attrs(soup: BeautifulSoup) -> dict[str, str]:
        """Read Craigslist's labelled attribute pairs into a dict."""
        attrs: dict[str, str] = {}

        class_map = {
            "auto_vin": "vin",
            "auto_make": "make",
            "auto_model": "model",
            "auto_year": "year",
            "auto_fuel_type": "fuel",
            "auto_transmission": "transmission",
            "auto_miles": "odometer",
            "condition": "condition",
        }

        for node in soup.select("div.attr, p.attr, span.attr"):
            classes = node.get("class", [])
            valu = node.select_one(".valu")
            value_text = valu.get_text(" ", strip=True) if valu else node.get_text(" ", strip=True)
            for css_class, key in class_map.items():
                if css_class in classes and value_text:
                    attrs.setdefault(key, value_text)

            labl = node.select_one(".labl")
            if labl and valu:
                label = labl.get_text(strip=True).rstrip(":").lower()
                if "odometer" in label:
                    attrs.setdefault("odometer", valu.get_text(strip=True))
                elif label == "vin":
                    attrs.setdefault("vin", valu.get_text(strip=True))
                elif label == "condition":
                    attrs.setdefault("condition", valu.get_text(strip=True))
                elif label in {"fuel"}:
                    attrs.setdefault("fuel", valu.get_text(strip=True))
                elif label in {"transmission"}:
                    attrs.setdefault("transmission", valu.get_text(strip=True))

        return attrs

    @staticmethod
    def _listing_id(url: str, node) -> str | None:
        legacy = _LEGACY_ID_RE.search(url)
        if legacy:
            return legacy.group(1)
        viewed = _VIEW_ID_RE.search(url)
        if viewed:
            return viewed.group(1)
        data_pid = node.get("data-pid")
        if data_pid:
            return str(data_pid)
        return None

    @staticmethod
    def _parse_price(node) -> float | None:
        if not node:
            return None
        match = _PRICE_RE.search(node.get_text())
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _parse_year(title: str) -> int | None:
        match = _YEAR_RE.search(title)
        return int(match.group(1)) if match else None
