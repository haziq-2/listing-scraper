"""Marketplace navigation helpers — open the Vehicles category feed."""

from __future__ import annotations

from loguru import logger

from scrapers.facebook.selectors import SELECTORS, primary
from scrapers.facebook.url_builder import build_vehicles_url
from services.city_resolver import ResolvedRegion

try:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeoutError
except ImportError:  # pragma: no cover
    PWError = Exception  # type: ignore[misc, assignment]
    PWTimeoutError = TimeoutError  # type: ignore[misc, assignment]


class MarketplaceNavigator:
    """Ensures the browser is on the Vehicles category feed before scraping."""

    def __init__(self, listing_wait_ms: int = 25_000) -> None:
        self.listing_wait_ms = listing_wait_ms
        self._listing_selector = primary(SELECTORS.listing_link)

    def ensure_vehicles_feed(self, page, region: ResolvedRegion) -> bool:
        """Activate Vehicles category when the page shows an empty generic search."""
        if self._has_listings(page):
            return True

        if self._is_empty_feed(page):
            logger.info("Marketplace shows empty search results; selecting Vehicles category.")

        if self._click_vehicles_category(page, region.facebook_slug):
            if self._wait_for_listings(page):
                logger.info("Vehicles feed loaded after category click.")
                return True
            logger.debug("Category click did not surface listings yet.")

        vehicles_url = build_vehicles_url(region)
        if page.url != vehicles_url:
            logger.info("Navigating to Vehicles URL: {}", vehicles_url)
            try:
                page.goto(vehicles_url, timeout=60_000, wait_until="domcontentloaded")
            except PWError as exc:
                logger.warning("Vehicles URL navigation failed: {}", exc)

        return self._wait_for_listings(page)

    def _click_vehicles_category(self, page, slug: str) -> bool:
        """Click the Vehicles entry in the Marketplace sidebar."""
        slug = (slug or "").lower()
        locators = [
            page.get_by_role("link", name="Vehicles", exact=True),
            page.locator(f"a[href*='/marketplace/{slug}/vehicles']"),
            page.locator("a[href*='/marketplace/category/vehicles']"),
            page.locator("a[href*='category=vehicles']"),
            page.locator("a").filter(has_text="Vehicles"),
        ]
        for locator in locators:
            try:
                if locator.count() == 0:
                    continue
                target = locator.first
                target.scroll_into_view_if_needed(timeout=5_000)
                target.click(timeout=8_000)
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
                logger.debug("Clicked Vehicles via {}", locator)
                return True
            except (PWError, PWTimeoutError) as exc:
                logger.debug("Vehicles click attempt failed: {}", exc)
                continue
            except Exception as exc:  # noqa: BLE001
                logger.debug("Vehicles click attempt failed: {}", exc)
                continue
        return False

    def _is_empty_feed(self, page) -> bool:
        if self._has_listings(page):
            return False
        try:
            body = (page.locator("body").inner_text(timeout=5_000) or "").lower()
        except Exception:  # noqa: BLE001
            return True
        return any(marker in body for marker in SELECTORS.empty_feed_markers)

    def _has_listings(self, page) -> bool:
        try:
            return page.locator(self._listing_selector).count() > 0
        except Exception:  # noqa: BLE001
            return False

    def _wait_for_listings(self, page) -> bool:
        if self._has_listings(page):
            return True
        try:
            page.wait_for_selector(self._listing_selector, timeout=self.listing_wait_ms)
            return True
        except PWTimeoutError:
            return False
        except Exception:  # noqa: BLE001
            return False
