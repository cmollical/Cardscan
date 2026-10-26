"""Persistent, serial, at-most-one-attempt vision worker."""

from contextlib import contextmanager
import fcntl
import os
import time
from pathlib import Path
import signal
import threading
from cardscan.app.store import Store
from cardscan.app.media import MediaStore
from cardscan.app.vision import Jobs
from cardscan.local_pricing.database import Database


@contextmanager
def worker_lock(db):
    path = Path(str(db.path) + ".vision.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A vision worker already owns this database")
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def process_one(jobs):
    if not jobs.settings.enabled or (jobs.db.path.parent / ".ai-restore-hold").exists():
        return False
    with jobs.db.connect(readonly=True) as c:
        row = c.execute(
            "SELECT id FROM vision_jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1"
        ).fetchone()
    if not row:
        return False
    return jobs.run(row["id"])


def serve(db, media_root, *, once=False, provider=None, settings=None, stop=None):
    stop = stop or threading.Event()
    jobs = Jobs(Store(db), MediaStore(db, media_root), settings, provider)
    with worker_lock(db):
        # queued rows have not been attempted; only in-flight requests are uncertain.
        jobs.recover(running_only=True)
        heartbeat = Path(str(db.path) + ".vision.heartbeat")
        try:
            while not stop.is_set():
                temporary = heartbeat.with_suffix(".heartbeat.tmp")
                temporary.write_text(str(time.time()))
                temporary.replace(heartbeat)
                worked = process_one(jobs)
                if once:
                    break
                if not worked:
                    stop.wait(1)
        finally:
            heartbeat.unlink(missing_ok=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    db = Database(os.environ["TALLYBINDER_DB"])
    if db.health()["status"] != "ok":
        raise RuntimeError("Migrate database before starting worker")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    serve(db, os.environ["TALLYBINDER_MEDIA_DIR"], once=args.once, stop=stop)


if __name__ == "__main__":
    main()
