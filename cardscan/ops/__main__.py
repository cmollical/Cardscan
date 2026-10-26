"""Private deployment CLI. No provisioning, paid calls or synchronization by default."""

import argparse
import json
import os
from pathlib import Path
from .backup import create, restore, validate_database
from .daily import run
from cardscan.local_pricing.database import Database, utc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--db", default=os.getenv("TALLYBINDER_DB", "local-evidence/tallybinder.sqlite")
    )
    p.add_argument(
        "--media",
        default=os.getenv("TALLYBINDER_MEDIA_DIR", "local-evidence/tallybinder-photos"),
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    ack = sub.add_parser("acknowledge-restore")
    ack.add_argument("--confirm-cost-review", action="store_true")
    m = sub.add_parser("migrate")
    m.add_argument("--backup-directory", required=True)
    a = sub.add_parser("approved-sets")
    a.add_argument("--output", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--config", required=True)
    d.add_argument("--execute", action="store_true")
    b = sub.add_parser("backup")
    b.add_argument("--destination", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--archive", required=True)
    r.add_argument("--destination", required=True)
    args = p.parse_args()
    if args.command == "restore":
        result = restore(args.archive, args.destination)
    else:
        db = Database(args.db)
        if not db.path.is_file():
            p.error(
                "Existing persistent database required; no blank database or demo seeding"
            )
        if args.command == "acknowledge-restore":
            if not args.confirm_cost_review:
                p.error(
                    "Explicit provider-usage and remaining-budget review is required"
                )
            hold = db.path.parent / ".ai-restore-hold"
            if hold.exists():
                (db.path.parent / "restore-clearance.json").write_text(
                    json.dumps(
                        {
                            "reviewed_at": utc(),
                            "action": "Operator acknowledged external usage and remaining budget",
                        }
                    )
                )
                hold.unlink()
            result = {"restore_hold_cleared": True, "paid_request_executed": False}
        elif args.command == "migrate":
            with db.connect(readonly=True) as c:
                version = c.execute("PRAGMA user_version").fetchone()[0]
            if version < 6:
                backup = create(db, args.media, args.backup_directory)
                db.migrate()
                result = {"migration_backup": backup, **db.health()}
            else:
                result = db.health()
        elif args.command == "check":
            from cardscan.app.security import CloudSettings

            CloudSettings.environment()
            validate_database(db.path)
            result = db.health()
            if result["status"] != "ok" or not result["products"] or not result["skus"]:
                p.error("Migrate and import the real pricing database before startup")
            Path(args.media).mkdir(parents=True, exist_ok=True, mode=0o700)
            with db.connect(readonly=True) as c:
                for row in c.execute("SELECT filename,content_hash FROM app_media"):
                    from .backup import digest

                    photo = Path(args.media) / row["filename"]
                    if (
                        not photo.is_file()
                        or photo.is_symlink()
                        or digest(photo) != row["content_hash"]
                    ):
                        p.error(
                            "Referenced media missing or corrupt; restore photos before startup"
                        )
        elif args.command == "approved-sets":
            output = Path(args.output)
            if output.exists():
                p.error("Approved set configuration already exists; edit deliberately")
            with db.connect(readonly=True) as c:
                rows = c.execute(
                    "SELECT provider,category_id,source_set_id FROM sync_state WHERE last_success_at IS NOT NULL ORDER BY category_id,source_set_id,provider"
                ).fetchall()
            grouped = {}
            for row in rows:
                grouped.setdefault(
                    (int(row["category_id"]), int(row["source_set_id"])), []
                ).append(row["provider"])
            if not grouped or len(grouped) > 15:
                p.error("Choose an explicit subset of up to 15 existing sets")
            result = {
                "version": 1,
                "max_requests": 64,
                "sets": [
                    {"category": cat, "group": group, "providers": names}
                    for (cat, group), names in grouped.items()
                ],
            }
            output.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(result, f, indent=2)
        elif args.command == "daily":
            result = run(db, args.config, execute=args.execute)
        else:
            result = create(db, args.media, args.destination)
    print(json.dumps(result, indent=2))
    if args.command == "daily" and args.execute and result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
