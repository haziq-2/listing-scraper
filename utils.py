"""Small shared helpers: anti-blocking delays, user-agent rotation, retries."""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from config import get_settings

T = TypeVar("T")


def random_user_agent() -> str:
    """Return a random realistic desktop user agent from the configured pool."""
    return random.choice(get_settings().user_agents)


def human_delay(min_seconds: float | None = None, max_seconds: float | None = None) -> None:
    """Sleep for a random duration to mimic human pacing between actions."""
    settings = get_settings()
    low = settings.min_action_delay if min_seconds is None else min_seconds
    high = settings.max_action_delay if max_seconds is None else max_seconds
    if high < low:
        low, high = high, low
    delay = random.uniform(low, high)
    logger.debug("Sleeping {:.2f}s (human delay)", delay)
    time.sleep(delay)


def jittered_interval(base_seconds: int, jitter_seconds: int) -> float:
    """Return ``base`` +/- a random jitter, floored at 1 second."""
    jitter = random.uniform(-jitter_seconds, jitter_seconds)
    return max(1.0, base_seconds + jitter)


def with_retries(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator applying exponential backoff with jitter to a callable.

    Uses settings from config for attempts and backoff bounds. Intended for
    network-bound operations that may transiently fail.
    """
    settings = get_settings()

    wrapped = retry(
        reraise=True,
        stop=stop_after_attempt(settings.retry_attempts),
        wait=wait_random_exponential(multiplier=settings.retry_backoff_base, max=settings.retry_backoff_max),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda state: logger.warning(
            "Retry {}/{} after error: {}",
            state.attempt_number,
            settings.retry_attempts,
            state.outcome.exception() if state.outcome else "unknown",
        ),
    )
    return wrapped(func)


CAPTCHA_MARKERS: tuple[str, ...] = (
    "captcha",
    "are you a human",
    "verify you are human",
    "unusual activity",
    "complete the security check",
    "recaptcha",
    "hcaptcha",
    "blocked",
    "access denied",
)


def looks_like_captcha(html_or_text: str) -> bool:
    """Heuristically detect CAPTCHA / bot-wall pages from page text."""
    if not html_or_text:
        return False
    lowered = html_or_text.lower()
    return any(marker in lowered for marker in CAPTCHA_MARKERS)
