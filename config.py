"""Central configuration for AutoWatch.

All tunable settings live here. Values can be overridden through environment
variables (optionally provided via a local ``.env`` file). Nothing else in the
codebase should read ``os.environ`` directly so this stays the single source of
truth.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def _env_str(key: str, default: str) -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _resolve(path_value: str) -> Path:
    """Resolve a possibly-relative path against the project root."""
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


# A pool of realistic, current desktop browser user agents. One is selected at
# random per scraper session to reduce trivial fingerprinting.
USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
)


class Settings(BaseModel):
    """Strongly-typed application settings."""

    # --- Paths ---
    db_path: Path = Field(default_factory=lambda: _resolve(_env_str("AUTOWATCH_DB_PATH", "data/vehicles.db")))
    log_dir: Path = Field(default_factory=lambda: _resolve(_env_str("AUTOWATCH_LOG_DIR", "logs")))

    # --- Logging ---
    log_level: str = Field(default_factory=lambda: _env_str("AUTOWATCH_LOG_LEVEL", "INFO").upper())

    # --- Polling / watch mode ---
    poll_interval_seconds: int = Field(default_factory=lambda: _env_int("AUTOWATCH_POLL_INTERVAL_SECONDS", 300))
    poll_jitter_seconds: int = Field(default_factory=lambda: _env_int("AUTOWATCH_POLL_JITTER_SECONDS", 60))

    # --- Generic anti-blocking delays (seconds) ---
    min_action_delay: float = Field(default_factory=lambda: _env_float("AUTOWATCH_MIN_ACTION_DELAY", 1.5))
    max_action_delay: float = Field(default_factory=lambda: _env_float("AUTOWATCH_MAX_ACTION_DELAY", 4.5))

    # --- Region / geocoding ---
    search_radius_km: float = Field(default_factory=lambda: _env_float("AUTOWATCH_SEARCH_RADIUS_KM", 80.0))
    craigslist_sites_cache_path: Path = Field(
        default_factory=lambda: _resolve(_env_str("AUTOWATCH_CRAIGSLIST_SITES_CACHE", "data/craigslist_sites.json"))
    )
    craigslist_sites_cache_ttl_hours: int = Field(
        default_factory=lambda: _env_int("AUTOWATCH_CRAIGSLIST_SITES_CACHE_TTL_HOURS", 168)
    )

    # --- Craigslist ---
    craigslist_min_delay: float = Field(default_factory=lambda: _env_float("AUTOWATCH_CRAIGSLIST_MIN_DELAY", 2.0))
    craigslist_max_delay: float = Field(default_factory=lambda: _env_float("AUTOWATCH_CRAIGSLIST_MAX_DELAY", 5.0))
    craigslist_max_listings: int = Field(default_factory=lambda: _env_int("AUTOWATCH_CRAIGSLIST_MAX_LISTINGS", 350))
    craigslist_fetch_details: bool = Field(default_factory=lambda: _env_bool("AUTOWATCH_CRAIGSLIST_FETCH_DETAILS", False))
    craigslist_request_timeout: int = Field(default_factory=lambda: _env_int("AUTOWATCH_CRAIGSLIST_REQUEST_TIMEOUT", 25))

    # --- OfferUp (US only; cars & trucks category 5.1) ---
    offerup_enabled: bool = Field(default_factory=lambda: _env_bool("AUTOWATCH_OFFERUP_ENABLED", True))
    offerup_max_listings: int = Field(default_factory=lambda: _env_int("AUTOWATCH_OFFERUP_MAX_LISTINGS", 100))
    offerup_page_size: int = Field(default_factory=lambda: _env_int("AUTOWATCH_OFFERUP_PAGE_SIZE", 50))
    offerup_category_id: str = Field(default_factory=lambda: _env_str("AUTOWATCH_OFFERUP_CATEGORY_ID", "5.1"))
    offerup_min_delay: float = Field(default_factory=lambda: _env_float("AUTOWATCH_OFFERUP_MIN_DELAY", 2.0))
    offerup_max_delay: float = Field(default_factory=lambda: _env_float("AUTOWATCH_OFFERUP_MAX_DELAY", 5.0))
    offerup_request_timeout: int = Field(default_factory=lambda: _env_int("AUTOWATCH_OFFERUP_REQUEST_TIMEOUT", 25))

    # --- Facebook Marketplace ---
    facebook_enabled: bool = Field(default_factory=lambda: _env_bool("AUTOWATCH_FACEBOOK_ENABLED", True))
    facebook_max_listings: int = Field(default_factory=lambda: _env_int("AUTOWATCH_FACEBOOK_MAX_LISTINGS", 100))
    facebook_headless: bool = Field(default_factory=lambda: _env_bool("AUTOWATCH_FACEBOOK_HEADLESS", False))
    facebook_profile_dir: Path = Field(
        default_factory=lambda: _resolve(_env_str("AUTOWATCH_FACEBOOK_PROFILE_DIR", "data/fb_profile"))
    )
    facebook_scroll_pause: float = Field(default_factory=lambda: _env_float("AUTOWATCH_FACEBOOK_SCROLL_PAUSE", 2.5))
    facebook_scroll_wait_ms: int = Field(default_factory=lambda: _env_int("AUTOWATCH_FACEBOOK_SCROLL_WAIT_MS", 2500))
    facebook_max_scrolls: int = Field(default_factory=lambda: _env_int("AUTOWATCH_FACEBOOK_MAX_SCROLLS", 25))
    facebook_scroll_stall_attempts: int = Field(
        default_factory=lambda: _env_int("AUTOWATCH_FACEBOOK_SCROLL_STALL_ATTEMPTS", 3)
    )
    facebook_auth_timeout_seconds: int = Field(
        default_factory=lambda: _env_int("AUTOWATCH_FACEBOOK_AUTH_TIMEOUT_SECONDS", 300)
    )
    # Use installed Google Chrome for better Facebook session persistence (recommended).
    # Set to "chrome" or "msedge". Leave empty to use Playwright's bundled Chromium.
    facebook_browser_channel: str = Field(
        default_factory=lambda: _env_str("AUTOWATCH_FACEBOOK_BROWSER_CHANNEL", "chrome")
    )

    # --- Database ---
    database_backend: str = Field(default_factory=lambda: _env_str("AUTOWATCH_DATABASE_BACKEND", "sqlite"))

    # --- Retry behaviour ---
    retry_attempts: int = Field(default_factory=lambda: _env_int("AUTOWATCH_RETRY_ATTEMPTS", 4))
    retry_backoff_base: float = Field(default_factory=lambda: _env_float("AUTOWATCH_RETRY_BACKOFF_BASE", 2.0))
    retry_backoff_max: float = Field(default_factory=lambda: _env_float("AUTOWATCH_RETRY_BACKOFF_MAX", 30.0))

    user_agents: tuple[str, ...] = USER_AGENTS

    def ensure_directories(self) -> None:
        """Create the directories required for the app to run."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.facebook_profile_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached, validated settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
