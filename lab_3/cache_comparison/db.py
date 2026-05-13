import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DbStats:
    reads: int
    writes: int


class SqliteDb:
    def __init__(self, db_path: str, artificial_delay_ms: float = 0.0) -> None:
        self._db_path = db_path
        self._delay_s = max(0.0, float(artificial_delay_ms) / 1000.0)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """.strip()
        )
        self._conn.commit()
        self._lock = threading.Lock()
        self._reads = 0
        self._writes = 0

    def get(self, item_id: str) -> Optional[str]:
        if self._delay_s > 0:
            time.sleep(self._delay_s)
        with self._lock:
            self._reads += 1
            cur = self._conn.execute("SELECT value_json FROM items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return str(row[0])

    def set(self, item_id: str, value_json: str) -> None:
        if self._delay_s > 0:
            time.sleep(self._delay_s)
        with self._lock:
            self._writes += 1
            self._conn.execute(
                """
                INSERT INTO items(id, value_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """.strip(),
                (item_id, value_json, time.time()),
            )
            self._conn.commit()

    def stats(self) -> DbStats:
        with self._lock:
            return DbStats(reads=self._reads, writes=self._writes)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

