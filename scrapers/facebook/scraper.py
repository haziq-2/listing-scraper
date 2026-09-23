"""Facebook Marketplace scraper orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from config import Settings, get_settings
from models import VehicleListing
from scrapers.facebook.auth import SessionManager
from scrapers.facebook.browser import persistent_browser
from scrapers.facebook.exceptions import (
    FacebookScraperError,
    MarketplaceNavigationError,
    PlaywrightUnavailableError,
    SecurityChallengeError,
    SessionExpiredError,
    TransientPageError,
)
from scrapers.facebook.extractor import MarketplaceExtractor
from scrapers.facebook.metrics import AuthState, ScrapeMetrics
from scrapers.facebook.navigation import MarketplaceNavigator
from scrapers.facebook.scroller import MarketplaceScroller, _is_transient_page_error
from scrapers.facebook.selectors import SELECTORS, primary
from scrapers.facebook.url_builder import build_search_url
from services.city_resolver import ResolvedRegion

try:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeoutError
except ImportError:  # pragma: no cover
    PWError = Exception  # type: ignore[misc, assignment]
    PWTimeoutError = TimeoutError  # type: ignore[misc, assignment]


@dataclass
class ScrapeResult:
    """Outcome of a Facebook scrape run."""

    listings: list[VehicleListing]
    metrics: ScrapeMetrics
    error: str | None = None


class FacebookScraper:
    """Scrapes vehicle listings from Facebook Marketplace for a region."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._extractor = MarketplaceExtractor()
        self._session = SessionManager(
            headless=self.settings.facebook_headless,
            auth_timeout_seconds=self.settings.facebook_auth_timeout_seconds,
        )
        self._scroller = MarketplaceScroller(
            self._extractor,
            max_listings=self.settings.facebook_max_listings,
            max_scrolls=self.settings.facebook_max_scrolls,
            stall_attempts=self.settings.facebook_scroll_stall_attempts,
            scroll_wait_ms=self.settings.facebook_scroll_wait_ms,
        )
        self._navigator = MarketplaceNavigator()

    def scrape(self, region: ResolvedRegion, query: str | None = None) -> list[VehicleListing]:
        """Scrape listings; returns empty list on failure (logs metrics)."""
        result = self.scrape_with_metrics(region, query=query)
        return result.listings

    def scrape_with_metrics(self, region: ResolvedRegion, query: str | None = None) -> ScrapeResult:
        metrics = ScrapeMetrics()
        search_url = build_search_url(region, query=query)
        logger.info("Facebook scraping: {}", search_url)

        try:
            with persistent_browser(self.settings) as (context, page):
                listings = self._run_scrape(context, page, search_url, region, metrics)
                metrics.log_summary(region.raw_input)
                return ScrapeResult(listings=listings, metrics=metrics)
        except PlaywrightUnavailableError as exc:
            logger.error("{}", exc)
            metrics.log_summary(region.raw_input)
            return ScrapeResult(listings=[], metrics=metrics, error=str(exc))
        except FacebookScraperError as exc:
            logger.error("Facebook scrape failed: {}", exc)
            metrics.log_summary(region.raw_input)
            return ScrapeResult(listings=[], metrics=metrics, error=str(exc))
        except PWTimeoutError as exc:
            logger.error("Facebook navigation timed out: {}", exc)
            metrics.log_summary(region.raw_input)
            return ScrapeResult(listings=[], metrics=metrics, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.error("Facebook scrape failed unexpectedly: {}", exc)
            metrics.log_summary(region.raw_input)
            return ScrapeResult(listings=[], metrics=metrics, error=str(exc))

    def _run_scrape(
        self,
        context,
        page,
        search_url: str,
        region: ResolvedRegion,
        metrics: ScrapeMetrics,
    ) -> list[VehicleListing]:
        cards: list[dict] = []
        try:
            if not self._open_marketplace(context, page, search_url, region, metrics):
                raise MarketplaceNavigationError("Could not open Marketplace search results.")

            cards = self._scroller.collect(page, metrics)
            listings = self._extractor.parse_cards(cards, region, metrics)

            if listings:
                logger.info("Facebook produced {} listing(s) for {}", len(listings), region.raw_input)
            else:
                logger.warning(
                    "Facebook returned 0 listings for {} (slug={}). "
                    "Check Marketplace location matches your region.",
                    region.raw_input,
                    region.facebook_slug,
                )
            return listings
        except PWError as exc:
            if _is_transient_page_error(exc) and cards:
                logger.warning("Returning partial results after transient error: {}", exc)
                return self._extractor.parse_cards(cards, region, metrics)
            raise TransientPageError(str(exc)) from exc

    def _open_marketplace(
        self,
        context,
        page,
        search_url: str,
        region: ResolvedRegion,
        metrics: ScrapeMetrics,
    ) -> bool:
        try:
            self._session.ensure_session(context, page, metrics)
        except SessionExpiredError as exc:
            logger.warning("{}", exc)
            return False

        if not self._goto_with_retry(page, search_url, metrics):
            return False

        self._warn_if_wrong_slug(page, region)

        if self._session._has_listings(page):
            metrics.auth_state = AuthState.AUTHENTICATED
            return True

        state = self._session.detect_auth_state(page, context)
        if state in (AuthState.SECURITY_CHALLENGE, AuthState.LOGIN_REQUIRED):
            try:
                self._session.ensure_authenticated(page, context, search_url, metrics)
            except (SessionExpiredError, SecurityChallengeError) as exc:
                logger.warning("{}", exc)
                return False

        if self._session._has_listings(page):
            metrics.auth_state = AuthState.AUTHENTICATED
            return True

        # A keyword search must stay on /search/. Falling back to /vehicles
        # drops the query and returns the unfiltered feed.
        if "/search" not in search_url and self._navigator.ensure_vehicles_feed(page, region):
            metrics.auth_state = AuthState.AUTHENTICATED
            return True

        if self._session._wait_for_listings(page):
            metrics.auth_state = AuthState.AUTHENTICATED
            return True

        logger.warning(
            "No Marketplace listings rendered. Complete any security prompts and retry."
        )
        return False

    def _goto_with_retry(self, page, url: str, metrics: ScrapeMetrics) -> bool:
        if self._session._on_security_page(page):
            logger.debug("On Facebook security page; skipping navigation.")
            return True

        attempts = self.settings.retry_attempts
        for attempt in range(1, attempts + 1):
            try:
                page.goto(url, timeout=60_000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PWTimeoutError:
                    pass
                if self._session._on_security_page(page):
                    return True
                return True
            except PWError as exc:
                metrics.retries += 1
                if _is_transient_page_error(exc):
                    logger.debug("Navigation interrupted (attempt {}/{}): {}", attempt, attempts, exc)
                    if self._session._has_listings(page) or "/marketplace/" in (page.url or ""):
                        return True
                    if attempt == attempts:
                        logger.error("Facebook navigation failed after retries: {}", exc)
                        return False
                    page.wait_for_timeout(int(self.settings.retry_backoff_base ** attempt * 1000))
                    continue
                if attempt == attempts:
                    logger.error("Facebook navigation failed: {}", exc)
                    return False
                page.wait_for_timeout(int(self.settings.retry_backoff_base ** attempt * 1000))
        return False

    @staticmethod
    def _warn_if_wrong_slug(page, region: ResolvedRegion) -> None:
        url = (page.url or "").lower()
        slug = region.facebook_slug.lower()
        if f"/marketplace/{slug}/" in url or f"/marketplace/{slug}?" in url:
            return
        if "/marketplace/category/" in url:
            logger.warning(
                "Facebook redirected to generic Marketplace (not '{}'). "
                "Results may reflect your account's saved location instead of '{}'.",
                slug,
                region.raw_input,
            )
