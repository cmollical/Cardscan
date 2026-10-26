"""Versioned SQLite storage. Monetary values are TEXT decimals, never REAL math."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

from cardscan.structured_prices import json_text


def utc(value=None):
    dt = datetime.now(timezone.utc) if value is None else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required')
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')


class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


class Database:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def connect(self, *, readonly=False):
        if readonly:
            c = sqlite3.connect('file:' + quote(str(self.path.resolve())) + '?mode=ro', uri=True, timeout=5, factory=ClosingConnection)
            c.execute('PRAGMA query_only=ON')
        else:
            c = sqlite3.connect(self.path, timeout=5, factory=ClosingConnection)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=5000')
        return c

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            version = c.execute('PRAGMA user_version').fetchone()[0]
            if version > 6:
                raise ValueError('Database newer than supported schema')
            if version == 0:
                # executescript transaction includes migration and version atomically.
                c.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('schema.sql').read_text() + '\nCOMMIT;')
            if version < 2:
                c.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('migrations').joinpath('002.sql').read_text() + '\nCOMMIT;')
            if version < 3:
                c.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('migrations').joinpath('003.sql').read_text() + '\nCOMMIT;')
            if version < 4:
                c.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('migrations').joinpath('004.sql').read_text() + '\nCOMMIT;')
            if version < 5:
                c.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('migrations').joinpath('005.sql').read_text() + '\nCOMMIT;')
            if version < 6:
                c.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('migrations').joinpath('006.sql').read_text() + '\nCOMMIT;')
            c.execute('PRAGMA journal_mode=WAL')

    @contextmanager
    def transaction(self):
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def document(self, c, *, url, payload, retrieved_at, original_hash=None, kind='original'):
        if not url.startswith('https://'):
            raise ValueError('HTTPS evidence URL required')
        stamp = utc(retrieved_at)
        digest = sha256(payload).hexdigest()
        source_hash = original_hash or digest
        if len(source_hash) != 64 or any(x not in '0123456789abcdef' for x in source_hash):
            raise ValueError('Invalid source content hash')
        if kind == 'original' and source_hash != digest:
            raise ValueError('Original response hash mismatch')
        c.execute('''INSERT INTO documents(url,content_hash,original_source_hash,payload,payload_kind,retrieved_at,last_checked_at)
                     VALUES(?,?,?,?,?,?,?) ON CONFLICT(url,content_hash) DO UPDATE SET last_checked_at=MAX(last_checked_at,excluded.last_checked_at)''',
                  (url,digest,source_hash,payload,kind,stamp,stamp))
        return c.execute('SELECT id FROM documents WHERE url=? AND content_hash=?',(url,digest)).fetchone()[0]

    def sync_status(self):
        with self.connect(readonly=True) as c:
            return [dict(r) for r in c.execute('SELECT * FROM sync_state ORDER BY provider,category_id,source_set_id')]

    def health(self):
        with self.connect(readonly=True) as c:
            version = c.execute('PRAGMA user_version').fetchone()[0]
            return {'status':'ok' if version == 6 else 'schema_mismatch','schema_version':version,
                    'products':c.execute('SELECT COUNT(*) FROM products').fetchone()[0],
                    'skus':c.execute('SELECT COUNT(*) FROM skus').fetchone()[0]}
