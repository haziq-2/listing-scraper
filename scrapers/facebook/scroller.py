"""Infinite-scroll collection with stall detection."""

from __future__ import annotations

from loguru import logger

from scrapers.facebook.extractor import MarketplaceExtractor
from scrapers.facebook.metrics import ScrapeMetrics
from scrapers.facebook.selectors import SELECTORS, primary

try:
    from playwright.sync_api import Error as PWError
except ImportError:  # pragma: no cover
    PWError = Exception  # type: ignore[misc, assignment]

_SCROLL_JS = """
() => {
    const links = document.querySelectorAll("a[href*='/marketplace/item/']");
    const last = links.length ? links[links.length - 1] : null;
    if (last) last.scrollIntoView({block: "end", inline: "nearest"});

    const roots = [];
    if (last) roots.push(last);
    for (const sel of %s) {
        const node = document.querySelector(sel);
        if (node) roots.push(node);
    }
    const seen = new Set();
    for (const start of roots) {
        let node = start;
        while (node && !seen.has(node)) {
            seen.add(node);
            const style = getComputedStyle(node);
            const canScroll = /(auto|scroll|overlay)/.test(style.overflowY)
                && node.scrollHeight > node.clientHeight + 40;
            if (canScroll) node.scrollBy(0, Math.max(1400, node.clientHeight * 0.85));
            node = node.parentElement;
        }
    }
    window.scrollBy(0, 1800);
    return true;
}
""" % list(SELECTORS.feed_container)


class MarketplaceScroller:
    """Scrolls Marketplace results until cap or repeated stall."""

    def __init__(
        self,
        extractor: MarketplaceExtractor,
        *,
        max_listings: int,
        max_scrolls: int,
        stall_attempts: int,
        scroll_wait_ms: int = 2500,
    ) -> None:
        self._extractor = extractor
        self.max_listings = max_listings
        self.max_scrolls = max_scrolls
        self.stall_attempts = stall_attempts
        self.scroll_wait_ms = scroll_wait_ms

    def collect(self, page, metrics: ScrapeMetrics) -> list[dict]:
        collected: dict[str, dict] = {}
        stalls = 0
        listing_selector = primary(SELECTORS.listing_link)

        try:
            page.wait_for_selector(listing_selector, timeout=30_000)
        except Exception:  # noqa: BLE001
            logger.debug("Initial listing selector wait timed out; continuing scroll.")

        for scroll_idx in range(self.max_scrolls):
            metrics.scroll_iterations = scroll_idx + 1
            try:
                cards = self._extractor.extract_cards_from_page(page)
            except PWError as exc:
                if _is_transient_page_error(exc):
                    logger.warning(
                        "Facebook page changed during scroll ({} cards saved); stopping.",
                        len(collected),
                    )
                    break
                raise

            before = len(collected)
            for card in cards:
                lid = card.get("listing_id")
                if lid:
                    collected.setdefault(str(lid), card)

            new_count = len(collected) - before
            logger.debug(
                "Scroll {}: {} new, {} unique total",
                scroll_idx + 1,
                new_count,
                len(collected),
            )

            if len(collected) >= self.max_listings:
                break

            if new_count == 0:
                stalls += 1
                metrics.scroll_stalls = stalls
                if stalls >= self.stall_attempts:
                    logger.info(
                        "Stopping scroll: no new listings after {} stall(s).",
                        stalls,
                    )
                    break
            else:
                stalls = 0
                metrics.scroll_stalls = 0

            try:
                page.evaluate(_SCROLL_JS)
                if new_count == 0:
                    page.keyboard.press("End")
                page.wait_for_timeout(self.scroll_wait_ms)
            except PWError as exc:
                if _is_transient_page_error(exc):
                    logger.warning("Scroll interrupted ({} cards saved).", len(collected))
                    break
                raise

        metrics.cards_extracted = len(collected)
        return list(collected.values())[: self.max_listings]


def _is_transient_page_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "execution context was destroyed",
            "navigation",
            "interrupted",
            "target closed",
            "frame was detached",
        )
    )
