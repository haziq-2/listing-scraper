"""Facebook session and authentication state detection."""

from __future__ import annotations

import time

from loguru import logger

from scrapers.facebook.exceptions import SecurityChallengeError, SessionExpiredError
from scrapers.facebook.metrics import AuthState, ScrapeMetrics
from scrapers.facebook.selectors import SELECTORS, primary

try:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeoutError
except ImportError:  # pragma: no cover
    PWError = Exception  # type: ignore[misc, assignment]
    PWTimeoutError = TimeoutError  # type: ignore[misc, assignment]

_FB_ORIGINS = (
    "https://www.facebook.com",
    "https://facebook.com",
    "https://m.facebook.com",
)
_FB_HOME = "https://www.facebook.com/"


class SessionManager:
    """Detects auth state and waits for interactive login when needed."""

    def __init__(
        self,
        *,
        headless: bool,
        auth_timeout_seconds: int = 300,
        listing_selector: str | None = None,
    ) -> None:
        self.headless = headless
        self.auth_timeout_seconds = auth_timeout_seconds
        self.listing_selector = listing_selector or primary(SELECTORS.listing_link)

    @staticmethod
    def is_logged_in(context) -> bool:
        """True when Facebook session cookie ``c_user`` is present."""
        try:
            cookies = context.cookies(list(_FB_ORIGINS))
            return any(c.get("name") == "c_user" and c.get("value") for c in cookies)
        except Exception:  # noqa: BLE001
            return False

    def detect_auth_state(self, page, context) -> AuthState:
        if self.is_logged_in(context):
            return AuthState.AUTHENTICATED
        url = (page.url or "").lower()
        if any(marker in url for marker in SELECTORS.auth_url_markers):
            return AuthState.SECURITY_CHALLENGE
        if self._needs_login_form(page):
            return AuthState.LOGIN_REQUIRED
        if self._has_listings(page):
            return AuthState.AUTHENTICATED
        return AuthState.UNKNOWN

    def log_auth_state(self, metrics: ScrapeMetrics, page, context) -> AuthState:
        state = self.detect_auth_state(page, context)
        metrics.auth_state = state
        logger.info("Facebook auth state: {}", state.value)
        return state

    def ensure_session(self, context, page, metrics: ScrapeMetrics) -> None:
        """Ensure a logged-in session exists before navigating to Marketplace."""
        if self.is_logged_in(context):
            metrics.auth_state = AuthState.AUTHENTICATED
            logger.debug("Facebook session cookie found.")
            return

        if self.headless:
            raise SessionExpiredError(
                "Facebook is not logged in. Run once with:\n"
                "  AUTOWATCH_FACEBOOK_HEADLESS=false python main.py --fb-login\n"
                "or complete login in a visible browser, then retry."
            )

        self._open_home_for_login(page)
        if self.is_logged_in(context):
            metrics.auth_state = AuthState.AUTHENTICATED
            logger.info("Facebook session active.")
            return

        self.wait_for_interactive_login(context, page, metrics)
        if not self.is_logged_in(context):
            raise SessionExpiredError(
                "Facebook login was not completed. Run: python main.py --fb-login"
            )
        metrics.auth_state = AuthState.AUTHENTICATED

    def wait_for_interactive_login(
        self,
        context,
        page,
        metrics: ScrapeMetrics | None = None,
    ) -> None:
        """Wait passively for the user to log in. Never reloads during the attempt."""
        logger.warning(
            "Facebook needs you to log in. Use the browser window on facebook.com — "
            "do not close it. The scraper will wait up to {}s and will NOT reload "
            "the page while you work through login or security checks.",
            self.auth_timeout_seconds,
        )
        deadline = time.monotonic() + self.auth_timeout_seconds
        while time.monotonic() < deadline:
            if self.is_logged_in(context):
                logger.info("Facebook login detected (session saved to profile).")
                page.wait_for_timeout(3_000)
                if metrics:
                    metrics.auth_state = AuthState.AUTHENTICATED
                return
            if self._has_listings(page):
                if metrics:
                    metrics.auth_state = AuthState.AUTHENTICATED
                return
            page.wait_for_timeout(2_000)

        if metrics:
            metrics.auth_state = AuthState.EXPIRED
        raise SessionExpiredError(
            f"Timed out after {self.auth_timeout_seconds}s waiting for Facebook login."
        )

    def ensure_authenticated(self, page, context, search_url: str, metrics: ScrapeMetrics) -> None:
        """Handle login/security pages encountered mid-navigation."""
        state = self.log_auth_state(metrics, page, context)
        if state == AuthState.AUTHENTICATED:
            return
        if state in (AuthState.SECURITY_CHALLENGE, AuthState.LOGIN_REQUIRED):
            if self.headless:
                raise SessionExpiredError(
                    "Facebook requires login or a security check. "
                    "Set AUTOWATCH_FACEBOOK_HEADLESS=false and complete auth in the browser."
                )
            self.wait_for_interactive_login(context, page, metrics)
            return
        if not self._wait_for_listings(page):
            raise SessionExpiredError("Facebook session expired or Marketplace did not load.")

    def _open_home_for_login(self, page) -> None:
        """Open facebook.com home (not Marketplace) so login persists correctly."""
        url = (page.url or "").lower()
        if self._on_security_page(page) or self._needs_login_form(page):
            return
        if "facebook.com" in url and not "/marketplace" in url:
            return
        try:
            logger.info("Opening facebook.com for login (not Marketplace).")
            page.goto(_FB_HOME, timeout=60_000, wait_until="domcontentloaded")
        except PWError as exc:
            logger.debug("Navigation to facebook.com: {}", exc)

    def _wait_for_listings(self, page) -> bool:
        if self._has_listings(page):
            return True
        try:
            page.wait_for_selector(self.listing_selector, timeout=20_000)
            return True
        except PWTimeoutError:
            return False
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _on_security_page(page) -> bool:
        url = (page.url or "").lower()
        return any(marker in url for marker in SELECTORS.auth_url_markers)

    @staticmethod
    def _needs_login_form(page) -> bool:
        if SessionManager._on_security_page(page):
            return True
        try:
            for sel in SELECTORS.login_password:
                if page.locator(sel).count() > 0:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    @staticmethod
    def _has_listings(page) -> bool:
        try:
            return page.locator(primary(SELECTORS.listing_link)).count() > 0
        except Exception:  # noqa: BLE001
            return False


def run_facebook_login(settings) -> int:
    """Interactive one-shot login; persists session to the Facebook profile directory."""
    from scrapers.facebook.browser import persistent_browser

    if settings.facebook_headless:
        logger.error(
            "Facebook login requires a visible browser. "
            "Set AUTOWATCH_FACEBOOK_HEADLESS=false and retry."
        )
        return 1

    session = SessionManager(
        headless=False,
        auth_timeout_seconds=settings.facebook_auth_timeout_seconds,
    )
    metrics = ScrapeMetrics()

    with persistent_browser(settings) as (context, page):
        session._open_home_for_login(page)
        if session.is_logged_in(context):
            logger.info(
                "Already logged in to Facebook. Profile: {}",
                settings.facebook_profile_dir,
            )
            return 0
        session.wait_for_interactive_login(context, page, metrics)
        logger.info(
            "Facebook login complete. Session saved to {}. "
            "You can now run scrapes without logging in again.",
            settings.facebook_profile_dir,
        )
    return 0
