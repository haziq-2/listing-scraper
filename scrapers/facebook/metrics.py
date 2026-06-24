"""Run metrics and structured reporting for Facebook scrapes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class AuthState(str, Enum):
    """Observed authentication state for a browser session."""

    UNKNOWN = "unknown"
    AUTHENTICATED = "authenticated"
    LOGIN_REQUIRED = "login_required"
    SECURITY_CHALLENGE = "security_challenge"
    EXPIRED = "expired"


@dataclass
class ScrapeMetrics:
    """Counters and timing for a single Facebook scrape run."""

    auth_state: AuthState = AuthState.UNKNOWN
    cards_extracted: int = 0
    listings_parsed: int = 0
    listings_kept: int = 0
    listings_skipped_location: int = 0
    extraction_failures: int = 0
    scroll_iterations: int = 0
    scroll_stalls: int = 0
    retries: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @property
    def duration_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def log_summary(self, region: str) -> None:
        logger.info(
            "Facebook run summary | region={} | auth={} | duration={:.1f}s | "
            "cards={} | parsed={} | kept={} | skipped_location={} | "
            "extraction_failures={} | scrolls={} | stalls={} | retries={}",
            region,
            self.auth_state.value,
            self.duration_seconds,
            self.cards_extracted,
            self.listings_parsed,
            self.listings_kept,
            self.listings_skipped_location,
            self.extraction_failures,
            self.scroll_iterations,
            self.scroll_stalls,
            self.retries,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "auth_state": self.auth_state.value,
            "duration_seconds": round(self.duration_seconds, 2),
            "cards_extracted": self.cards_extracted,
            "listings_parsed": self.listings_parsed,
            "listings_kept": self.listings_kept,
            "listings_skipped_location": self.listings_skipped_location,
            "extraction_failures": self.extraction_failures,
            "scroll_iterations": self.scroll_iterations,
            "scroll_stalls": self.scroll_stalls,
            "retries": self.retries,
        }
