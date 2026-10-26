"""Consistent SQLite + immutable referenced photos, checksummed and restore-tested."""

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
from tempfile import TemporaryDirectory
from uuid import uuid4
from cardscan.local_pricing.database import Database, utc


def digest(path):
    h = sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_database(path):
    db = Database(path)
    with db.connect(readonly=True) as c:
        if (
            c.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or c.execute("PRAGMA foreign_key_check").fetchone()
        ):
            raise ValueError("Backup database integrity failed")
        return [
            dict(r)
            for r in c.execute(
                "SELECT id,filename,content_hash,bytes FROM app_media ORDER BY id"
            )
        ]


def create(db, media_root, directory):
    root = Path(media_root).resolve()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / (
        "tallybinder-"
        + utc().replace(":", "").replace("+", "_")
        + "-"
        + uuid4().hex[:8]
        + ".tar"
    )
    with db.connect(readonly=True) as c:
        db_bytes = (
            c.execute("PRAGMA page_count").fetchone()[0]
            * c.execute("PRAGMA page_size").fetchone()[0]
        )
        photo_bytes = c.execute(
            "SELECT coalesce(sum(bytes),0) FROM app_media"
        ).fetchone()[0]
    if shutil.disk_usage(directory).free < 2 * db_bytes + photo_bytes + 100_000_000:
        raise ValueError(
            "Insufficient disk headroom for consistent snapshot and archive"
        )
    with TemporaryDirectory(prefix="tallybinder-backup-", dir=directory) as tmp:
        snapshot = Path(tmp) / "database.sqlite"
        with db.connect(readonly=True) as source, sqlite3.connect(snapshot) as dest:
            source.backup(dest, pages=256, sleep=0.01)
        photos = validate_database(snapshot)
        required = snapshot.stat().st_size + sum(p["bytes"] for p in photos)
        if shutil.disk_usage(directory).free < required + 100_000_000:
            raise ValueError(
                "Insufficient disk for complete backup; existing backups retained"
            )
        files = {
            "database.sqlite": {
                "sha256": digest(snapshot),
                "bytes": snapshot.stat().st_size,
            }
        }
        for row in photos:
            name = row["filename"]
            source = (root / name).resolve()
            if (
                Path(name).name != name
                or source.parent != root
                or not source.is_file()
                or (root / name).is_symlink()
            ):
                raise ValueError("Unsafe or missing media in backup")
            value = digest(source)
            if value != row["content_hash"] or source.stat().st_size != row["bytes"]:
                raise ValueError("Media differs from database provenance")
            files["photos/" + name] = {"sha256": value, "bytes": row["bytes"]}
        manifest = {
            "format": "tallybinder-backup-v1",
            "created_at": utc(),
            "schema_version": db.health()["schema_version"],
            "files": files,
        }
        manifest_path = Path(tmp) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True))
        partial = target.with_suffix(".part")
        try:
            fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out, tarfile.open(fileobj=out, mode="w") as tar:
                tar.add(manifest_path, arcname="manifest.json", recursive=False)
                tar.add(snapshot, arcname="database.sqlite", recursive=False)
                for row in photos:
                    tar.add(
                        root / row["filename"],
                        arcname="photos/" + row["filename"],
                        recursive=False,
                    )
            partial.replace(target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    return {
        "path": str(target),
        "sha256": digest(target),
        "bytes": target.stat().st_size,
        "photos": len(photos),
        "created_at": manifest["created_at"],
    }


def restore(archive, destination, *, max_bytes=200_000_000_000):
    target = Path(destination).resolve()
    if target.exists():
        raise ValueError(
            "Restore destination must not exist; never overwrite live data"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / (".restore-" + uuid4().hex)
    staging.mkdir(mode=0o700)
    try:
        with tarfile.open(archive, "r:*") as tar:
            members = {}
            total = 0
            for member in tar:
                if (
                    not member.isfile()
                    or member.name in members
                    or member.name.startswith("/")
                    or ".." in Path(member.name).parts
                ):
                    raise ValueError("Unsafe backup archive member")
                if member.name not in ("manifest.json", "database.sqlite") and not (
                    member.name.startswith("photos/")
                    and len(Path(member.name).parts) == 2
                    and Path(member.name).suffix == ".jpg"
                ):
                    raise ValueError("Unexpected backup archive member")
                total += member.size
                if total > max_bytes:
                    raise ValueError("Restore exceeds configured disk allowance")
                members[member.name] = member
            if (
                "manifest.json" not in members
                or members["manifest.json"].size > 10_000_000
            ):
                raise ValueError("Invalid manifest")
            manifest = json.load(tar.extractfile(members["manifest.json"]))
            if manifest.get("format") != "tallybinder-backup-v1" or set(members) != set(
                manifest["files"]
            ) | {"manifest.json"}:
                raise ValueError("Backup file manifest mismatch")
            if shutil.disk_usage(target.parent).free < total + 100_000_000:
                raise ValueError("Not enough disk space for restore")
            for name, info in manifest["files"].items():
                path = staging / name
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as out, tar.extractfile(
                    members[name]
                ) as source:
                    shutil.copyfileobj(source, out, length=1024 * 1024)
                if (
                    path.stat().st_size != info["bytes"]
                    or digest(path) != info["sha256"]
                ):
                    raise ValueError("Backup checksum mismatch")
            photos = validate_database(staging / "database.sqlite")
            if set("photos/" + p["filename"] for p in photos) != set(
                manifest["files"]
            ) - {"database.sqlite"}:
                raise ValueError("Database/media manifest mismatch")
            for p in photos:
                info = manifest["files"]["photos/" + p["filename"]]
                if info["sha256"] != p["content_hash"] or info["bytes"] != p["bytes"]:
                    raise ValueError("Restored media does not match database")
            (staging / "photos").mkdir(exist_ok=True, mode=0o700)
            # A backup can predate an API attempt. Never replay restored authorizations.
            with Database(staging / "database.sqlite").transaction() as c:
                quarantined = c.execute(
                    "UPDATE vision_jobs SET status='interrupted',error='disaster_restore_manual_review_reserve_held',finished_at=? WHERE status IN ('queued','running')",
                    (utc(),),
                ).rowcount
            hold = {
                "reason": "Restore cannot establish API usage after its snapshot; reconcile provider spend and explicitly approve resumption.",
                "created_at": utc(),
                "quarantined_jobs": quarantined,
            }
            (staging / ".ai-restore-hold").write_text(json.dumps(hold))
            manifest["restore"] = {
                **hold,
                "restored_database_sha256": digest(staging / "database.sqlite"),
            }
            (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "destination": str(target),
        "photos": len(photos),
        "schema_version": manifest["schema_version"],
        "ai_resume_requires_cost_review": True,
        "quarantined_jobs": quarantined,
    }
