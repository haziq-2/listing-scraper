"""Repository tests."""

import tempfile
from pathlib import Path

from models import Source, VehicleListing
from storage.sqlite import SQLiteVehicleRepository


def test_upsert_many_dedupes():
    with tempfile.TemporaryDirectory() as tmp:
        repo = SQLiteVehicleRepository(Path(tmp) / "test.db")
        listing = VehicleListing(
            source=Source.FACEBOOK,
            listing_id="abc",
            title="Test Car",
            listing_url="https://www.facebook.com/marketplace/item/abc",
            price=10000.0,
            currency="USD",
        )
        new_ids, updated = repo.upsert_many([listing])
        assert listing.listing_id in new_ids
        assert updated == 0

        new_ids2, updated2 = repo.upsert_many([listing])
        assert listing.listing_id not in new_ids2
        assert updated2 == 1
        repo.close()
