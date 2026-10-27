import os
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cardscan.cloud.daily import configured_scopes, execute
from cardscan.cloud.snapshot import PricingSnapshot
from cardscan.local_pricing.cli import seed
from cardscan.local_pricing.database import Database


class FakeBlob:
    def __init__(self, source=None, generation=1):
        self.source = Path(source) if source else None
        self.generation = generation
        self.metadata = None
        self.cache_control = None
        self.upload_match = None

    def exists(self, timeout=None):
        return self.source is not None

    def reload(self, timeout=None):
        if self.source is None:
            raise FileNotFoundError

    def download_to_filename(self, target, timeout=None):
        copyfile(self.source, target)

    def upload_from_filename(
        self,
        source,
        content_type=None,
        if_generation_match=None,
        timeout=None,
    ):
        self.upload_match = if_generation_match
        self.source = Path(source).with_suffix(".published")
        copyfile(source, self.source)
        self.generation = (self.generation + 1) if if_generation_match else 1


class FakeBucket:
    def __init__(self, blob):
        self.value = blob

    def blob(self, name):
        return self.value


class ServerlessTests(unittest.TestCase):
    def test_snapshot_downloads_and_validates_generation(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.sqlite"
            db = Database(source)
            db.migrate()
            seed(db)
            with db.connect() as connection:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            target = Path(tmp) / "runtime" / "database.sqlite"
            snapshot = PricingSnapshot(
                FakeBucket(FakeBlob(source, generation=7)),
                path=target,
                refresh_seconds=0,
            )
            result = snapshot.ensure().health()
            self.assertEqual(result["status"], "ok")
            self.assertEqual(snapshot.generation, 7)

    def test_daily_bootstrap_publishes_with_create_precondition(self):
        blob = FakeBlob()

        def import_fixture(db, scopes, **kwargs):
            seed(db)
            return {"status": "success", "sets": [], "requests": 0}

        with patch("cardscan.cloud.daily.synchronize", side_effect=import_fixture):
            result = execute(FakeBucket(blob))
        self.assertTrue(result["published"])
        self.assertEqual(blob.upload_match, 0)
        self.assertGreater(result["health"]["products"], 0)

    def test_scopes_are_explicit_bounded_pokemon_ids(self):
        with patch.dict(os.environ, {"TALLYBINDER_DAILY_SCOPES": "3:604,85:23599"}):
            self.assertEqual(configured_scopes(), [(3, 604), (85, 23599)])
        for value in ("4:1", "3:0", ",".join(f"3:{x}" for x in range(1, 17))):
            with self.subTest(value=value), patch.dict(
                os.environ, {"TALLYBINDER_DAILY_SCOPES": value}
            ):
                with self.assertRaises(ValueError):
                    configured_scopes()


if __name__ == "__main__":
    unittest.main()
