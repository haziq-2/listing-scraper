"""SQLite implementation of VehicleRepository with schema migrations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from loguru import logger

from models import Source, VehicleListing
from storage.base import VehicleRepository

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteVehicleRepository(VehicleRepository):
    """SQLite-backed vehicle store with versioned migrations."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._run_migrations()
        logger.debug("SQLite repository initialised at {}", self.db_path)

    def _run_migrations(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row[0]
            for row in self._conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        for path in migration_files:
            version = int(path.stem.split("_")[0])
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                self._conn.executescript(sql)
            except sqlite3.OperationalError as exc:
                # Idempotent ALTER on re-run (column already exists).
                if "duplicate column" not in str(exc).lower():
                    raise
            self._conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _utcnow_iso()),
            )
            self._conn.commit()
            logger.info("Applied migration {}", path.name)

    def exists(self, source: Source | str, listing_id: str) -> bool:
        source_value = source.value if isinstance(source, Source) else str(source)
        row = self._conn.execute(
            "SELECT 1 FROM vehicles WHERE source = ? AND listing_id = ? LIMIT 1",
            (source_value, listing_id),
        ).fetchone()
        return row is not None

    def known_listing_ids(self, source: Source | str) -> set[str]:
        source_value = source.value if isinstance(source, Source) else str(source)
        rows = self._conn.execute(
            "SELECT listing_id FROM vehicles WHERE source = ?",
            (source_value,),
        ).fetchall()
        return {str(row["listing_id"]) for row in rows}

    def upsert(self, listing: VehicleListing) -> bool:
        new_ids, _ = self.upsert_many([listing])
        return listing.listing_id in new_ids

    def upsert_many(self, listings: Iterable[VehicleListing]) -> tuple[set[str], int]:
        """Batch upsert. Returns (new_listing_ids, updated_count)."""
        now = _utcnow_iso()
        new_ids: set[str] = set()
        updated_count = 0
        cursor = self._conn.cursor()
        for listing in listings:
            source_value = listing.source_value
            if self.exists(source_value, listing.listing_id):
                cursor.execute(
                    """
                    UPDATE vehicles SET
                        last_seen = ?,
                        title = COALESCE(?, title),
                        price = COALESCE(?, price),
                        currency = COALESCE(?, currency),
                        year = COALESCE(?, year),
                        location = COALESCE(?, location),
                        image_url = COALESCE(?, image_url),
                        raw_payload = COALESCE(?, raw_payload)
                    WHERE source = ? AND listing_id = ?
                    """,
                    (
                        now,
                        listing.title,
                        listing.price,
                        listing.currency,
                        listing.year,
                        listing.location,
                        listing.image_url,
                        listing.raw_payload,
                        source_value,
                        listing.listing_id,
                    ),
                )
                updated_count += 1
            else:
                cursor.execute(
                    """
                    INSERT INTO vehicles (
                        source, listing_id, title, price, currency, year, make, model, mileage,
                        location, seller_name, listing_url, image_url, posted_time,
                        vin, condition, fuel, transmission, raw_payload, first_seen, last_seen
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        source_value,
                        listing.listing_id,
                        listing.title,
                        listing.price,
                        listing.currency,
                        listing.year,
                        listing.make,
                        listing.model,
                        listing.mileage,
                        listing.location,
                        listing.seller_name,
                        listing.listing_url,
                        listing.image_url,
                        listing.posted_time,
                        listing.vin,
                        listing.condition,
                        listing.fuel,
                        listing.transmission,
                        listing.raw_payload,
                        now,
                        now,
                    ),
                )
                new_ids.add(listing.listing_id)
        self._conn.commit()
        return new_ids, updated_count

    def count(self, source: str | None = None) -> int:
        if source:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM vehicles WHERE source = ?",
                (source,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM vehicles").fetchone()
        return int(row["c"]) if row else 0

    def list_all(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM vehicles"
        params: list[object] = []
        if source:
            sql += " WHERE source = ?"
            params.append(source)
        sql += " ORDER BY first_seen DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        return list(self._conn.execute(sql, params).fetchall())

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SQLiteVehicleRepository":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
