"""Local cache of raw stats.nba.com responses.

The gather step (network) writes here; the build step (offline) only reads.
Responses are stored verbatim (zlib-compressed JSON) so the build can be
re-run any number of times, and re-parsed if a parser changes, without
touching the network again.
"""

import json
import sqlite3
import time
import zlib
from pathlib import Path


def request_key(endpoint, params):
    return endpoint + "?" + json.dumps(params, sort_keys=True, separators=(",", ":"))


class RawStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS raw ("
            " key TEXT PRIMARY KEY, endpoint TEXT NOT NULL, params TEXT NOT NULL,"
            " fetched_at REAL NOT NULL, payload BLOB NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS failures ("
            " key TEXT PRIMARY KEY, endpoint TEXT NOT NULL, params TEXT NOT NULL,"
            " failed_at REAL NOT NULL, error TEXT NOT NULL)"
        )
        self._conn.commit()

    def close(self):
        self._conn.close()

    def has(self, endpoint, params):
        row = self._conn.execute(
            "SELECT 1 FROM raw WHERE key = ?", (request_key(endpoint, params),)
        ).fetchone()
        return row is not None

    def put(self, endpoint, params, payload):
        key = request_key(endpoint, params)
        blob = zlib.compress(json.dumps(payload).encode("utf-8"), 6)
        self._conn.execute(
            "INSERT OR REPLACE INTO raw (key, endpoint, params, fetched_at, payload)"
            " VALUES (?, ?, ?, ?, ?)",
            (key, endpoint, json.dumps(params, sort_keys=True), time.time(), blob),
        )
        self._conn.execute("DELETE FROM failures WHERE key = ?", (key,))
        self._conn.commit()

    def get(self, endpoint, params):
        row = self._conn.execute(
            "SELECT payload FROM raw WHERE key = ?", (request_key(endpoint, params),)
        ).fetchone()
        if row is None:
            raise KeyError(f"not in raw cache: {request_key(endpoint, params)}")
        return json.loads(zlib.decompress(row[0]).decode("utf-8"))

    def record_failure(self, endpoint, params, error):
        self._conn.execute(
            "INSERT OR REPLACE INTO failures (key, endpoint, params, failed_at, error)"
            " VALUES (?, ?, ?, ?, ?)",
            (request_key(endpoint, params), endpoint, json.dumps(params, sort_keys=True),
             time.time(), str(error)),
        )
        self._conn.commit()

    def failures(self):
        return self._conn.execute(
            "SELECT endpoint, params, error FROM failures ORDER BY endpoint"
        ).fetchall()
