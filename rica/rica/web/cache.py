"""SQLite cache for pages and searches (§8.6): pages 24 h (news 1 h), searches 1 h."""

import json
import sqlite3
import time
from pathlib import Path

PAGE_TTL = 24 * 3600
NEWS_PAGE_TTL = 3600
SEARCH_TTL = 3600


class WebCache:
    def __init__(self, path: Path):
        self.path = path
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires REAL, value TEXT)")

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def get(self, key: str):
        with self._db() as db:
            row = db.execute("SELECT value, expires FROM cache WHERE key = ?", (key,)).fetchone()
        if not row or row[1] < time.time():
            return None
        return json.loads(row[0])

    def put(self, key: str, value, ttl: float) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (key, time.time() + ttl, json.dumps(value))
            )
            db.execute("DELETE FROM cache WHERE expires < ?", (time.time() - 86400,))
