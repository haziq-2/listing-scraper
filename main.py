"""AutoWatch CLI entrypoint.

Discovers newly-listed vehicles on Facebook Marketplace and Craigslist for a
given city, persists what it has seen, and reports only the new listings.

Examples:
    python main.py --region "Dallas, TX"
    python main.py --region "London, UK"
    python main.py --region "Toronto, ON" --watch
    python main.py --list
    python main.py --list --source craigslist --limit 20
    python main.py --region "Austin, TX" --make Toyota --model Camry --max-price 25000 --min-year 2019
"""

from __future__ import annotations

import argparse
import sys
import time

from loguru import logger

from config import Settings, get_settings
from database import Database
from models import VehicleListing
from scrapers.craigslist import CraigslistScraper
from scrapers.facebook import FacebookScraper
from services.city_resolver import RegionResolver, ResolvedRegion
from services.deduplicator import Deduplicator, ScanStats, SearchFilters
from services.notifier import ConsoleNotifier
from utils import jittered_interval


def configure_logging(settings: Settings) -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, enqueue=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    logger.add(
        settings.log_dir / "autowatch_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="14 days",
        enqueue=True,
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="autowatch",
        description="Monitor newly listed vehicles on Facebook Marketplace and Craigslist.",
    )
    parser.add_argument(
        "--region",
        "--city",
        dest="region",
        metavar="REGION",
        help='Region to monitor, e.g. "Dallas, TX", "London, UK", "Bay Area"',
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Show all stored vehicles from the database and exit.",
    )
    parser.add_argument(
        "--source",
        choices=("craigslist", "facebook"),
        default=None,
        help="Filter --list output by source.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max vehicles to show with --list (default: all).",
    )
    parser.add_argument(
        "--max-listings",
        type=int,
        default=None,
        help="Max listings to scrape per source (overrides config defaults).",
    )
    parser.add_argument("--watch", action="store_true", help="Run continuously, polling on an interval.")
    parser.add_argument("--interval", type=int, default=None, help="Watch interval in seconds (default from config).")
    parser.add_argument(
        "--radius",
        type=float,
        default=None,
        help="Search radius in km for Facebook Marketplace (default from config).",
    )

    parser.add_argument(
        "--fb-login",
        action="store_true",
        help="Log in to Facebook once (visible browser), save session, and exit.",
    )

    parser.add_argument("--make", default=None, help="Filter by make, e.g. Toyota")
    parser.add_argument("--model", default=None, help="Filter by model, e.g. Camry")
    parser.add_argument("--max-price", type=float, default=None, help="Maximum price filter")
    parser.add_argument("--min-year", type=int, default=None, help="Minimum model year filter")

    parser.add_argument("--no-facebook", action="store_true", help="Skip Facebook Marketplace this run.")
    parser.add_argument("--no-craigslist", action="store_true", help="Skip Craigslist this run.")

    args = parser.parse_args(argv)
    if args.list:
        if args.region:
            parser.error("--list cannot be combined with --region")
        if args.watch:
            parser.error("--list cannot be combined with --watch")
        if args.fb_login:
            parser.error("--list cannot be combined with --fb-login")
    elif args.fb_login:
        if args.region:
            parser.error("--fb-login cannot be combined with --region")
        if args.watch:
            parser.error("--fb-login cannot be combined with --watch")
    elif not args.region:
        parser.error("--region is required unless using --list or --fb-login")
    return args


def list_stored_vehicles(settings: Settings, args: argparse.Namespace) -> int:
    """Print all vehicles saved in the SQLite database."""
    db = Database(settings.db_path)
    try:
        total = db.count(source=args.source)
        rows = db.list_all(source=args.source, limit=args.limit)
        ConsoleNotifier().print_inventory(rows, total=total, showing=len(rows))
    finally:
        db.close()
    return 0


class AutoWatch:
    """Wires the scrapers, deduplicator and notifier into a single run loop."""

    def __init__(self, settings: Settings, args: argparse.Namespace) -> None:
        self.settings = settings
        self.args = args
        if args.max_listings is not None:
            self.settings.craigslist_max_listings = args.max_listings
            self.settings.facebook_max_listings = args.max_listings
        self.db = Database(settings.db_path)
        self.deduplicator = Deduplicator(self.db)
        self.notifier = ConsoleNotifier()
        self.filters = SearchFilters(
            make=args.make,
            model=args.model,
            max_price=args.max_price,
            min_year=args.min_year,
        )
        self.run_facebook = settings.facebook_enabled and not args.no_facebook
        self.run_craigslist = not args.no_craigslist

    def run_once(self, region: ResolvedRegion) -> list[VehicleListing]:
        scraped: list[VehicleListing] = []

        # Sequential scraping only (no parallelism) per anti-blocking policy.
        if self.run_craigslist:
            try:
                scraped.extend(CraigslistScraper(self.settings).scrape(region))
            except Exception as exc:  # noqa: BLE001
                logger.error("Craigslist scraper crashed: {}", exc)

        if self.run_facebook:
            try:
                fb_result = FacebookScraper(self.settings).scrape_with_metrics(region)
                scraped.extend(fb_result.listings)
                if fb_result.error:
                    logger.warning("Facebook completed with error: {}", fb_result.error)
                logger.info("Facebook metrics: {}", fb_result.metrics.as_dict())
            except Exception as exc:  # noqa: BLE001
                logger.error("Facebook scraper crashed: {}", exc)

        new_listings, stats = self.deduplicator.process(scraped, self.filters)
        self.notifier.notify_many(new_listings, stats=stats, db_total=self.db.count())
        return new_listings

    def watch(self, region: ResolvedRegion) -> None:
        base_interval = self.args.interval or self.settings.poll_interval_seconds
        jitter = self.settings.poll_jitter_seconds
        logger.info("Watch mode on. Interval ~{}s (+/-{}s jitter). Ctrl+C to stop.", base_interval, jitter)
        cycle = 0
        while True:
            cycle += 1
            logger.info("=== Watch cycle {} ===", cycle)
            try:
                self.run_once(region)
            except Exception as exc:  # noqa: BLE001
                logger.error("Cycle {} failed: {}", cycle, exc)

            sleep_for = jittered_interval(base_interval, jitter)
            logger.info("Next cycle in {:.0f}s", sleep_for)
            time.sleep(sleep_for)

    def close(self) -> None:
        self.db.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings)

    if args.list:
        return list_stored_vehicles(settings, args)

    if args.fb_login:
        from scrapers.facebook.auth import run_facebook_login

        return run_facebook_login(settings)

    try:
        region = RegionResolver().resolve(args.region, radius_km=args.radius)
    except ValueError as exc:
        logger.error("Invalid region: {}", exc)
        return 2

    app = AutoWatch(settings, args)
    logger.info(
        "AutoWatch starting | region='{}' | craigslist={} | db has {} listing(s)",
        region.display_name,
        region.craigslist_area_name,
        app.db.count(),
    )

    try:
        if args.watch:
            app.watch(region)
        else:
            app.run_once(region)
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
