"""Cloud Run Job entry point for a bounded, atomic daily pricing refresh."""

import json
import os
from pathlib import Path
import tempfile

from cardscan.local_pricing.database import Database
from cardscan.local_pricing.discovery import discover
from cardscan.local_pricing.sync import DailyClient, synchronize

def configured_scopes():
    raw = os.getenv("TALLYBINDER_DAILY_SCOPES", "")
    if not raw.strip():
        return None
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


def discovered_scopes(db, catalog, *, limit=14, expansion=10):
    """Choose a bounded, rotating catalog batch without naming particular sets."""
    if not 1 <= limit <= 14 or not 1 <= expansion <= limit:
        raise ValueError("Invalid bounded catalog plan")
    successful = {
        (int(row["category_id"]), int(row["source_set_id"])): row["last_success_at"]
        for row in db.sync_status()
        if row["last_success_at"]
    }
    rows = [row for row in catalog["sets"] if row.get("providers")]

    def newest(row):
        return (row.get("published_on") or "", row["group"])

    selected = []
    # Split expansion capacity across language catalogs, then use any spare slots.
    unseen = [row for row in rows if (row["category"], row["group"]) not in successful]
    for category in (3, 85):
        category_rows = sorted(
            (row for row in unseen if row["category"] == category),
            key=newest,
            reverse=True,
        )
        selected.extend(category_rows[: expansion // 2])
    for row in sorted(unseen, key=newest, reverse=True):
        if len(selected) >= expansion:
            break
        if row not in selected:
            selected.append(row)

    # Keep recent imported sets fresh while the older catalog expands over time.
    imported = sorted(
        (row for row in rows if (row["category"], row["group"]) in successful),
        key=newest,
        reverse=True,
    )
    for row in imported:
        if len(selected) >= limit:
            break
        selected.append(row)
    return selected


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
        max_requests = int(os.getenv("TALLYBINDER_DAILY_MAX_REQUESTS", "64"))
        if not 1 <= max_requests <= 64:
            raise ValueError("Daily request budget must be between 1 and 64")
        client = DailyClient(db, max_requests=max_requests)
        scopes = configured_scopes()
        if scopes is None:
            selection = discovered_scopes(db, discover(db, client=client))
            scopes = [(row["category"], row["group"]) for row in selection]
            provider_scopes = {
                (row["category"], row["group"]): tuple(row["providers"])
                for row in selection
            }
        else:
            provider_scopes = {scope: ("tcgcsv", "tcgtracking") for scope in scopes}
        result = synchronize(
            db,
            scopes,
            client=client,
            resume=True,
            provider_scopes=provider_scopes,
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
