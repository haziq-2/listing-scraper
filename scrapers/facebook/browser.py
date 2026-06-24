"""Playwright persistent browser context management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from loguru import logger

from config import Settings
from scrapers.facebook.exceptions import PlaywrightUnavailableError
from utils import random_user_agent

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]


def stable_user_agent(profile_dir) -> str:
    """Keep one user agent per persistent profile to avoid security loops."""
    ua_file = profile_dir / "user_agent.txt"
    if ua_file.exists():
        return ua_file.read_text(encoding="utf-8").strip()
    ua = random_user_agent()
    profile_dir.mkdir(parents=True, exist_ok=True)
    ua_file.write_text(ua, encoding="utf-8")
    return ua


def _launch_kwargs(settings: Settings, user_agent: str) -> dict:
    kwargs: dict = {
        "user_data_dir": str(settings.facebook_profile_dir),
        "headless": settings.facebook_headless,
        "user_agent": user_agent,
        "viewport": {"width": 1366, "height": 900},
        "locale": "en-US",
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    channel = (settings.facebook_browser_channel or "").strip()
    if channel:
        kwargs["channel"] = channel
    return kwargs


@contextmanager
def persistent_browser(settings: Settings) -> Iterator:
    """Launch a persistent Chromium context and yield (context, page)."""
    if sync_playwright is None:
        raise PlaywrightUnavailableError(
            "Playwright is not installed. Run 'pip install playwright' and 'playwright install chromium'."
        )

    user_agent = stable_user_agent(settings.facebook_profile_dir)
    logger.debug("Using persistent Facebook profile at {}", settings.facebook_profile_dir)
    if settings.facebook_browser_channel:
        logger.debug("Using browser channel: {}", settings.facebook_browser_channel)

    with sync_playwright() as pw:
        launch_kwargs = _launch_kwargs(settings, user_agent)
        try:
            context = pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:
            if launch_kwargs.pop("channel", None):
                logger.warning(
                    "Failed to launch '{}' ({}). Falling back to bundled Chromium.",
                    settings.facebook_browser_channel,
                    exc,
                )
                context = pw.chromium.launch_persistent_context(**launch_kwargs)
            else:
                raise

        page = context.pages[0] if context.pages else context.new_page()
        try:
            yield context, page
        finally:
            # Brief pause so Chromium flushes cookies to the profile on disk.
            try:
                page.wait_for_timeout(2_000)
            except Exception:  # noqa: BLE001
                pass
            context.close()
