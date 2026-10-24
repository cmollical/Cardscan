"""SQLite cache and atomic conservative budget reservations; no network operations."""
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path
import sqlite3
import time
import uuid


class BudgetError(ValueError):
    pass


def micros(amount):
    return int((Decimal(str(amount)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


class ResearchStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, created REAL, payload TEXT);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, day TEXT, reserved INTEGER, charged INTEGER,
                    status TEXT, audit TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def cached(self, key, ttl_seconds, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            row = db.execute('SELECT created,payload FROM cache WHERE key=?', (key,)).fetchone()
        if row and 0 <= now - row[0] < ttl_seconds:
            return json.loads(row[1])
        return None

    def put(self, key, payload, now=None):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',
                       (key, time.time() if now is None else now, json.dumps(payload, allow_nan=False)))

    def reserve(self, day, amount, *, per_request, daily, max_requests):
        reserve = micros(amount)
        if reserve > micros(per_request):
            raise BudgetError('Conservative request reservation exceeds per-request spending limit')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used, count = db.execute('SELECT COALESCE(SUM(COALESCE(charged,reserved)),0),COUNT(*) '
                                     'FROM requests WHERE day=?', (day,)).fetchone()
            if used + reserve > micros(daily) or count >= max_requests:
                raise BudgetError('Daily spending or request limit would be exceeded')
            request_id = uuid.uuid4().hex
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?)',
                       (request_id, day, reserve, None, 'reserved', '{}'))
        return request_id

    def settle(self, request_id, actual_estimate, status, audit):
        # Unknown usage (timeout, process crash, malformed usage) retains the full
        # reservation. Do not assume an errored request incurred zero charges.
        with self.connect() as db:
            db.execute('UPDATE requests SET charged=?,status=?,audit=? WHERE id=?',
                       (None if actual_estimate is None else micros(actual_estimate), status,
                        json.dumps(audit, allow_nan=False), request_id))

    def ledger(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,day,reserved,charged,status,audit FROM requests ORDER BY rowid').fetchall()
        return [dict(id=r[0], day=r[1], reserved_usd=str(Decimal(r[2])/1_000_000),
                     charged_estimate_usd=None if r[3] is None else str(Decimal(r[3])/1_000_000),
                     status=r[4], audit=json.loads(r[5])) for r in rows]
