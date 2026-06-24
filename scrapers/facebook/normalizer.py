"""Price, location, and field normalization for Facebook listings."""

from __future__ import annotations

import re
from typing import Any

_PRICE_RE = re.compile(
    r"(?P<currency>\$|USD|CA\$|A\$)\s?(?P<amount>[\d,]+)|^(?P<amount_plain>[\d,]+)\s*(?P<currency_suffix>USD)$",
    re.I,
)
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")


def listing_id_from_href(href: str) -> str | None:
    match = _ITEM_ID_RE.search(href or "")
    return match.group(1) if match else None


def parse_price(lines: list[str]) -> tuple[float | None, str | None]:
    """Return (amount, currency_code) from card text lines."""
    for line in lines:
        match = _PRICE_RE.search(line)
        if not match:
            continue
        raw = match.group("amount") or match.group("amount_plain")
        if not raw:
            continue
        currency_token = match.group("currency") or match.group("currency_suffix") or "$"
        currency = _normalize_currency(currency_token)
        try:
            return float(raw.replace(",", "")), currency
        except ValueError:
            continue
    return None, None


def _normalize_currency(token: str) -> str:
    token = token.upper().strip()
    if token in {"$", "USD"}:
        return "USD"
    if token in {"CA$", "CAD"}:
        return "CAD"
    if token in {"A$", "AUD"}:
        return "AUD"
    return token


def parse_title(lines: list[str]) -> str | None:
    for line in lines:
        if "$" in line or re.search(r"\bUSD\b", line, re.I):
            continue
        if len(line.strip()) >= 4:
            return line.strip()
    return None


def parse_location(lines: list[str]) -> str | None:
    for line in reversed(lines):
        if "$" in line:
            continue
        text = line.strip()
        if len(text) >= 3:
            return text
    return None


def parse_year(title: str) -> int | None:
    match = _YEAR_RE.search(title)
    return int(match.group(1)) if match else None


def validate_listing_fields(
    *,
    listing_id: str | None,
    title: str | None,
    listing_url: str | None,
) -> list[str]:
    """Return validation error messages; empty list means valid."""
    errors: list[str] = []
    if not listing_id:
        errors.append("missing listing_id")
    if not title or not title.strip():
        errors.append("missing title")
    if not listing_url or "/marketplace/item/" not in listing_url:
        errors.append("invalid listing_url")
    return errors


def normalize_card_raw(card: dict[str, Any]) -> dict[str, Any]:
    """Preserve raw card payload for debugging while ensuring JSON-serializable keys."""
    return {
        "listing_id": card.get("listing_id"),
        "href": card.get("href"),
        "lines": list(card.get("lines") or []),
        "image": card.get("image"),
    }
