CREATE TABLE IF NOT EXISTS vehicles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,
    listing_id    TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    price         REAL,
    year          INTEGER,
    make          TEXT,
    model         TEXT,
    mileage       INTEGER,
    location      TEXT,
    seller_name   TEXT,
    listing_url   TEXT    NOT NULL,
    image_url     TEXT,
    posted_time   TEXT,
    vin           TEXT,
    condition     TEXT,
    fuel          TEXT,
    transmission  TEXT,
    first_seen    TEXT    NOT NULL,
    last_seen     TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicles_source_listing
    ON vehicles (source, listing_id);
