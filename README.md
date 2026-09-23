# AutoWatch

AutoWatch monitors **newly listed vehicles** on **Facebook Marketplace** and
**Craigslist** for a region you specify, and reports only listings it has not seen
before. State is kept in a local SQLite database so "new" means new across runs.

## Features

- **Any region worldwide** — pass a city, metro, or country (e.g. `"Dallas, TX"`,
  `"London, UK"`, `"Toronto, ON"`, `"Sydney, Australia"`).
- **Smart Craigslist matching** — downloads and caches all 700+ official Craigslist
  regional sites, with country-aware disambiguation (e.g. London UK vs London ON).
- **Facebook city-scoped search** — resolves a region to a Marketplace city slug
  (e.g. `dallas`, `austin`, `sanfrancisco`) and opens the Vehicles category feed
  with a configurable radius in miles.
- Craigslist scraping via `requests` + `BeautifulSoup` (all cars+trucks via `cta`),
  with optional detail-page enrichment (VIN, mileage, fuel, transmission).
- Facebook Marketplace scraping via Playwright with a **persistent profile** so
  you log in only once; automatic Vehicles category selection when the feed is empty.
- Accurate new-listing detection through a SQLite upsert keyed on
  `(source, listing_id)`.
- Optional filters: `--make`, `--model`, `--max-price`, `--min-year`.
- Continuous `--watch` mode with jittered polling intervals.
- Structured logging, per-run Facebook metrics, and schema migrations.
- Practical anti-blocking: stable user agent per Facebook profile, randomized delays,
  exponential backoff retries, rate limiting, and CAPTCHA detection.

## Requirements

- Python 3.12+ (recommended; some dependencies may not install on 3.14+)
- See `requirements.txt`

## Setup

```bash
# 1. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install the Playwright browser (needed for Facebook)
playwright install chromium

# 4. (Optional) copy and edit configuration
cp .env.example .env
```

## Usage

```bash
# One-off scan (any region)
python main.py --region "Dallas, TX"
python main.py --region "London, UK"
python main.py --region "Toronto, ON"

# Continuous watch mode
python main.py --region "Dallas, TX" --watch

# Wider Facebook search radius (km)
python main.py --region "Phoenix, AZ" --radius 120

# With filters (applied before showing new listings)
python main.py --region "Austin, TX" --make Toyota --model Camry --max-price 25000 --min-year 2019

# Limit how many listings each source scrapes per run
python main.py --region "Dallas, TX" --max-listings 200

# Craigslist only (no browser / no Facebook login needed)
python main.py --region "Dallas, TX" --no-facebook

# Facebook only
python main.py --region "Dallas, TX" --no-craigslist

# View all stored vehicles from the database
python main.py --list
python main.py --list --source craigslist
python main.py --list --source facebook --limit 20

# --city is an alias for --region
python main.py --city "Dallas, TX"
```

### First Facebook run

Facebook requires an authenticated session. **Log in once** using the dedicated login command:

```bash
AUTOWATCH_FACEBOOK_HEADLESS=false python main.py --fb-login
```

1. A browser opens to **facebook.com** (not Marketplace).
2. Log in and complete any security checks.
3. Wait until you see the message `Facebook login complete` in the terminal.
4. The session is saved to `data/fb_profile/` and reused on every later run.

Then scrape normally:

```bash
python main.py --region "Dallas, TX" --no-craigslist
```

**Tips for login persistence:**

- Use **Google Chrome** via `AUTOWATCH_FACEBOOK_BROWSER_CHANNEL=chrome` (default). Facebook
  sessions are more reliable than Playwright's bundled Chromium.
- Do **not** delete `data/fb_profile/` between runs — that is your saved session.
- If login keeps looping, reset the profile and log in again:
  ```bash
  rm -rf data/fb_profile
  python main.py --fb-login
  ```
- Keep the browser window open until the terminal says login is complete.

**Never commit Facebook credentials.** Sign in interactively; the profile stores
the session locally.

### Understanding output

- **NEW VEHICLE FOUND** — a listing AutoWatch had not seen before (first insert into the DB).
- **No new vehicles this cycle** — listings were scraped but all were already in the database.
- **`--list` → First seen** — UTC timestamp when AutoWatch first discovered that listing
  (not necessarily when the seller originally posted it).

## Configuration

All settings live in `config.py` and can be overridden via environment variables
(or a `.env` file). See `.env.example` for the full list.

| Variable                                   | Default            | Description                                     |
| ------------------------------------------ | ------------------ | ----------------------------------------------- |
| `AUTOWATCH_DB_PATH`                        | `data/vehicles.db` | SQLite database location                        |
| `AUTOWATCH_SEARCH_RADIUS_KM`               | `80`               | Facebook search radius (converted to FB miles)  |
| `AUTOWATCH_CRAIGSLIST_MAX_LISTINGS`        | `350`              | Max Craigslist listings per run                 |
| `AUTOWATCH_FACEBOOK_MAX_LISTINGS`          | `100`              | Max Facebook listings per run                   |
| `AUTOWATCH_FACEBOOK_MAX_SCROLLS`           | `25`               | Max infinite-scroll iterations                  |
| `AUTOWATCH_FACEBOOK_SCROLL_STALL_ATTEMPTS` | `3`                | Stop scrolling after N passes with no new cards |
| `AUTOWATCH_FACEBOOK_SCROLL_WAIT_MS`        | `2500`             | Wait after each scroll (ms)                     |
| `AUTOWATCH_FACEBOOK_HEADLESS`              | `false`            | Run Facebook browser headless                   |
| `AUTOWATCH_FACEBOOK_PROFILE_DIR`           | `data/fb_profile`  | Persistent browser profile                      |
| `AUTOWATCH_FACEBOOK_AUTH_TIMEOUT_SECONDS`  | `300`              | Interactive login wait timeout                  |
| `AUTOWATCH_POLL_INTERVAL_SECONDS`          | `300`              | Watch mode base interval                        |
| `AUTOWATCH_LOG_LEVEL`                      | `INFO`             | Console log level                               |

## Project structure

```
.
├── main.py                      # CLI + watch loop
├── config.py                    # Settings (env-overridable)
├── database.py                  # Facade over SQLite repository
├── models.py                    # Pydantic models
├── utils.py                     # Delays, UA rotation, retries
├── scrapers/
│   ├── craigslist.py            # requests + BeautifulSoup
│   └── facebook/                # Modular Playwright scraper
│       ├── scraper.py           # Orchestrator
│       ├── navigation.py        # Vehicles category + URL handling
│       ├── auth.py              # Session / login detection
│       ├── browser.py           # Persistent Chromium context
│       ├── extractor.py         # Card → VehicleListing
│       ├── scroller.py          # Infinite scroll + stall detection
│       ├── normalizer.py        # Price / location parsing
│       ├── selectors.py         # Centralized DOM selectors
│       └── metrics.py           # Per-run scrape statistics
├── storage/
│   ├── base.py                  # VehicleRepository interface
│   ├── sqlite.py                # SQLite + migrations
│   └── migrations/              # Versioned schema changes
├── services/
│   ├── city_resolver.py         # Region → Craigslist site + FB slug
│   ├── craigslist_sites.py      # Worldwide Craigslist site index
│   ├── facebook_locations.py    # FB slug + location filter tokens
│   ├── geocoder.py              # OpenStreetMap Nominatim
│   ├── deduplicator.py          # New-listing detection + filters
│   └── notifier.py              # Console output
├── tests/                       # Unit / integration tests
├── data/                        # SQLite DB + FB profile (gitignored)
└── logs/                        # Rotating logs (gitignored)
```

## Database

SQLite stores one row per `(source, listing_id)`. Key columns:

| Column               | Description                                   |
| -------------------- | --------------------------------------------- |
| `first_seen`         | When AutoWatch first discovered the listing   |
| `last_seen`          | Most recent scrape that included this listing |
| `price` / `currency` | Parsed listing price                          |
| `raw_payload`        | Raw Facebook card JSON (debugging)            |

Migrations run automatically on startup via `storage/migrations/`.

To reset and treat all future listings as new:

```bash
rm data/vehicles.db
```

## Tests

```bash
python -m pytest tests/ -v
```

## Troubleshooting

### Facebook keeps asking to log in

1. Run the dedicated login flow and wait for confirmation:
   ```bash
   AUTOWATCH_FACEBOOK_HEADLESS=false python main.py --fb-login
   ```
2. Use Chrome, not bundled Chromium: `AUTOWATCH_FACEBOOK_BROWSER_CHANNEL=chrome`
3. Reset the profile if the session is corrupted:
   ```bash
   rm -rf data/fb_profile
   python main.py --fb-login
   ```

### Facebook returns 0 listings

- Run with `AUTOWATCH_FACEBOOK_HEADLESS=false` and complete login/security prompts.
- Confirm vehicle cards appear manually in the browser window.
- Check logs for `Facebook run summary` metrics (`auth`, `cards`, `scrolls`).

### Only ~10 Facebook listings

Facebook often renders one screenful (~10 cards) before scroll loads more. Increase
scroll patience:

```bash
AUTOWATCH_FACEBOOK_SCROLL_STALL_ATTEMPTS=6 \
AUTOWATCH_FACEBOOK_MAX_SCROLLS=40 \
AUTOWATCH_FACEBOOK_SCROLL_WAIT_MS=4000 \
python main.py --region "Dallas, TX" --no-craigslist
```

### Prices show $0 or $1

Some sellers use placeholder prices ("contact for price"). AutoWatch stores the
value shown on the listing card; open the URL to verify the real price.

### `dquote>` in the terminal

Your shell is waiting for a closing double quote. Finish the quoted string or press
`Ctrl+C` to cancel.

## Notes on responsible use

AutoWatch implements only _practical_ anti-blocking (polite rate limiting,
human-like pacing, session reuse). It does **not** attempt to bypass CAPTCHAs or
defeat security systems — when a CAPTCHA/checkpoint is detected it pauses that
source and logs a warning. Review and respect each site's Terms of Service and
`robots.txt` before scraping.

caffeinate -is env AUTOWATCH_FACEBOOK_HEADLESS=true python main.py --region "San Antonio,
TX" --watch --interval 600

sqlite3 -header -csv data/vehicles.db "SELECT \* FROM vehicles;" > listings.csv
