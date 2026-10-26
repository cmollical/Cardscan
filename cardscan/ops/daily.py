"""Bounded daily sync of explicitly approved, already-imported provider/set scopes."""

import json
import os
from pathlib import Path
import shutil
from cardscan.local_pricing.sync import DailyClient, synchronize


def plan(db, config):
    if config.get("version") != 1:
        raise ValueError("Unsupported daily sync configuration")
    scopes = config.get("sets", [])
    if not scopes or len(scopes) > 15:
        raise ValueError(
            "Approve 1..15 existing sets; no automatic full-catalog expansion"
        )
    budget = config.get("max_requests")
    if type(budget) is not int or not 1 <= budget <= 64:
        raise ValueError("Daily request budget must be 1..64")
    if len({(x["category"], x["group"]) for x in scopes}) != len(scopes):
        raise ValueError("Duplicate daily set scope")
    providers = {}
    with db.connect(readonly=True) as c:
        for row in scopes:
            cat, group = row["category"], row["group"]
            if (
                type(cat) is not int
                or type(group) is not int
                or cat not in (3, 85)
                or group <= 0
            ):
                raise ValueError("Exact Pokemon set identifiers required")
            names = row.get("providers")
            if (
                not isinstance(names, list)
                or not names
                or len(set(names)) != len(names)
                or not set(names) <= {"tcgcsv", "tcgtracking"}
            ):
                raise ValueError("Explicit supported providers required")
            for name in names:
                old = c.execute(
                    "SELECT last_success_at FROM sync_state WHERE provider=? AND category_id=? AND source_set_id=?",
                    (name, str(cat), str(group)),
                ).fetchone()
                if not old or not old[0]:
                    raise ValueError(
                        "Daily sync cannot introduce unimported provider/set scopes"
                    )
            providers[(cat, group)] = tuple(names)
    return {
        "scopes": sorted(providers),
        "provider_scopes": providers,
        "max_requests": budget,
        "maximum_export_requests": sum(2 * len(x) for x in providers.values())
        + 1
        + len({x[0] for x in providers}),
    }


def run(db, path, *, execute=False, client=None):
    config = json.loads(Path(path).read_text())
    p = plan(db, config)
    if not execute:
        return {
            **p,
            "provider_scopes": [
                {"category": c, "group": g, "providers": list(v)}
                for (c, g), v in p["provider_scopes"].items()
            ],
            "execute": False,
        }
    if shutil.disk_usage(db.path.parent).free < max(
        2_000_000_000, db.path.stat().st_size // 5
    ):
        raise RuntimeError("Insufficient disk headroom; last valid dataset retained")
    result = synchronize(
        db,
        p["scopes"],
        client=client or DailyClient(db, max_requests=p["max_requests"]),
        resume=True,
        provider_scopes=p["provider_scopes"],
    )
    # Caller/timer sees partial failures rather than a successful exit code.
    return result
