"""Centralized Playwright/CSS selectors for Facebook Marketplace.

Update this file when Facebook changes DOM structure. Fallback selectors are
listed in priority order.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FacebookSelectors:
    """All selectors used by the Facebook scraper."""

    listing_link: tuple[str, ...] = (
        "a[href*='/marketplace/item/']",
    )
    feed_container: tuple[str, ...] = (
        '[role="feed"]',
        '[role="main"]',
    )
    login_password: tuple[str, ...] = (
        "input[name='pass']",
        "input#pass",
    )
    listing_image: tuple[str, ...] = (
        "img",
    )

    # Sidebar / navigation to the Vehicles category.
    vehicles_category_link: tuple[str, ...] = (
        "a[href*='/marketplace/category/vehicles']",
        "a[href*='/vehicles']",
        "a[href*='category=vehicles']",
    )

    # Visible text when FB loads generic search with no listings.
    empty_feed_markers: tuple[str, ...] = (
        "no products in your area",
        "there are currently no products",
        "check again later",
    )

    # URL fragments indicating auth / security pages.
    auth_url_markers: tuple[str, ...] = (
        "/login.php",
        "/login/",
        "/login?",
        "checkpoint",
        "two_step_verification",
        "two-factor",
        "confirmemail",
        "/recover",
    )


SELECTORS = FacebookSelectors()


def primary(selector_group: tuple[str, ...]) -> str:
    """Return the first selector in a fallback group."""
    return selector_group[0]
