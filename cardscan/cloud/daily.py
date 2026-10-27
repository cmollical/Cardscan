"""Cloud Run Job entry point for a bounded, atomic daily pricing refresh."""

import json
import os
from pathlib import Path
import tempfile

from cardscan.local_pricing.database import Database
from cardscan.local_pricing.sync import DailyClient, synchronize

DEFAULT_SCOPES = ((3, 23228), (3, 23237), (3, 604), (3, 630), (85, 23599))


def configured_scopes():
    raw = os.getenv("TALLYBINDER_DAILY_SCOPES", "")
    if not raw.strip():
        return list(DEFAULT_SCOPES)
    scopes = []
    for value in raw.split(","):
        category, group = value.strip().split(":", 1)
        pair = (int(category), int(group))
        if pair[0] not in (3, 85) or pair[1] <= 0:
            raise ValueError("Only explicit Pokemon category:set scopes are allowed")
        scopes.append(pair)
    if not 1 <= len(set(scopes)) <= 15:
        raise ValueError("Approve between one and fifteen unique daily scopes")
    return sorted(set(scopes))


def execute(bucket=None):
    if bucket is None:
        from google.cloud import storage

        bucket = storage.Client().bucket(os.environ["TALLYBINDER_STORAGE_BUCKET"])
    object_name = os.getenv("TALLYBINDER_PRICING_OBJECT", "pricing/database.sqlite")
    blob = bucket.blob(object_name)
    generation = 0
    with tempfile.TemporaryDirectory(prefix="tallybinder-sync-") as directory:
        path = Path(directory) / "database.sqlite"
        if blob.exists(timeout=30):
            blob.reload(timeout=30)
            generation = int(blob.generation)
            blob.download_to_filename(path, timeout=120)
        db = Database(path)
        db.migrate()
        scopes = configured_scopes()
        max_requests = int(os.getenv("TALLYBINDER_DAILY_MAX_REQUESTS", "64"))
        if not 1 <= max_requests <= 64:
            raise ValueError("Daily request budget must be between 1 and 64")
        result = synchronize(
            db,
            scopes,
            client=DailyClient(db, max_requests=max_requests),
            resume=True,
            provider_scopes={scope: ("tcgcsv", "tcgtracking") for scope in scopes},
        )
        if result.get("status") != "success":
            raise RuntimeError("Pricing synchronization did not complete successfully")
        with db.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        health = db.health()
        if health["status"] != "ok" or not health["products"] or not health["skus"]:
            raise RuntimeError("Refusing to publish an empty pricing snapshot")
        blob.metadata = {
            "schema_version": str(health["schema_version"]),
            "products": str(health["products"]),
            "skus": str(health["skus"]),
            "sync_status": result["status"],
        }
        blob.cache_control = "no-store"
        blob.upload_from_filename(
            path,
            content_type="application/vnd.sqlite3",
            if_generation_match=generation,
            timeout=300,
        )
        return {
            "published": True,
            "generation": int(blob.generation),
            "health": health,
            "sync": result,
        }


def main():
    print(json.dumps(execute(), indent=2))


if __name__ == "__main__":
    main()
