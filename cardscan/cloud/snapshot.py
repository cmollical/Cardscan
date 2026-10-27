"""Atomic Cloud Storage transport for the read-only pricing SQLite snapshot."""

import os
from pathlib import Path
import sqlite3
import threading
import time

from cardscan.local_pricing.database import Database


class PricingSnapshot:
    def __init__(
        self,
        bucket=None,
        *,
        object_name=None,
        path=None,
        refresh_seconds=None,
    ):
        if bucket is None:
            from google.cloud import storage

            bucket = storage.Client().bucket(os.environ["TALLYBINDER_STORAGE_BUCKET"])
        self.bucket = bucket
        self.object_name = object_name or os.getenv(
            "TALLYBINDER_PRICING_OBJECT", "pricing/database.sqlite"
        )
        self.path = Path(
            path or os.getenv("TALLYBINDER_DB", "/tmp/tallybinder/database.sqlite")
        )
        self.refresh_seconds = int(
            refresh_seconds
            if refresh_seconds is not None
            else os.getenv("TALLYBINDER_SNAPSHOT_REFRESH_SECONDS", "300")
        )
        self.generation = None
        self._last_check = 0.0
        self._lock = threading.Lock()

    def _validate(self, path):
        db = Database(path)
        result = db.health()
        if result["status"] != "ok" or not result["products"] or not result["skus"]:
            raise ValueError("Pricing snapshot is empty or incompatible")
        with sqlite3.connect(path) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Pricing snapshot failed integrity check")
        return result

    def refresh(self, *, force=False):
        now = time.monotonic()
        if (
            not force
            and self.path.exists()
            and now - self._last_check < self.refresh_seconds
        ):
            return False
        with self._lock:
            now = time.monotonic()
            if (
                not force
                and self.path.exists()
                and now - self._last_check < self.refresh_seconds
            ):
                return False
            blob = self.bucket.blob(self.object_name)
            blob.reload(timeout=30)
            generation = int(blob.generation)
            self._last_check = now
            if self.path.exists() and generation == self.generation:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.path.with_suffix(".download")
            temporary.unlink(missing_ok=True)
            try:
                blob.download_to_filename(temporary, timeout=120)
                self._validate(temporary)
                temporary.replace(self.path)
                self.generation = generation
            finally:
                temporary.unlink(missing_ok=True)
            return True

    def ensure(self):
        self.refresh(force=True)
        return Database(self.path)
