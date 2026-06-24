"""SQLite persistence layer for AutoWatch.

Thin facade over ``storage.sqlite.SQLiteVehicleRepository`` for backward
compatibility with existing imports.
"""

from __future__ import annotations

from pathlib import Path

from storage.sqlite import SQLiteVehicleRepository


class Database(SQLiteVehicleRepository):
    """Owns the SQLite connection and all vehicle persistence operations."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)

    def recent(self, limit: int = 20):
        return self.list_all(limit=limit)
