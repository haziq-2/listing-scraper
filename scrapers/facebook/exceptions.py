"""Facebook scraper exceptions."""

from __future__ import annotations


class FacebookScraperError(Exception):
    """Base error for Facebook Marketplace scraping."""


class PlaywrightUnavailableError(FacebookScraperError):
    """Playwright is not installed."""


class SessionExpiredError(FacebookScraperError):
    """Persistent session is missing or expired; interactive login required."""


class SecurityChallengeError(FacebookScraperError):
    """Facebook presented login, 2FA, or checkpoint — user action required."""


class MarketplaceNavigationError(FacebookScraperError):
    """Failed to reach Marketplace search results."""


class TransientPageError(FacebookScraperError):
    """Page context destroyed or navigation interrupted; may be retried."""
