import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from cache_comparison.cache import InMemoryCache
from cache_comparison.db import SqliteDb


@dataclass(frozen=True)
class StrategyMetrics:
    strategy: str
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    cache_size: int
    db_reads: int
    db_writes: int
    writeback_pending_keys: Optional[int]
    writeback_max_pending_keys: Optional[int]
    writeback_enqueued_writes: Optional[int]
    writeback_flushed_writes: Optional[int]
    writeback_flush_errors: Optional[int]
    writeback_last_flush_ts: Optional[float]


class StorageStrategy:
    def get(self, item_id: str) -> Optional[Any]:
        raise NotImplementedError()

    def set(self, item_id: str, value: Any) -> None:
        raise NotImplementedError()

    def metrics(self) -> StrategyMetrics:
        raise NotImplementedError()

    def close(self) -> None:
        return None


class CacheAsideWriteAroundStrategy(StorageStrategy):
    def __init__(self, db: SqliteDb, cache: InMemoryCache) -> None:
        self._db = db
        self._cache = cache

    def get(self, item_id: str) -> Optional[Any]:
        found, value = self._cache.get(item_id)
        if found:
            return value

        value_json = self._db.get(item_id)
        if value_json is None:
            return None
        value_obj = json.loads(value_json)
        self._cache.set(item_id, value_obj)
        return value_obj

    def set(self, item_id: str, value: Any) -> None:
        value_json = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        self._db.set(item_id, value_json)
        self._cache.delete(item_id)

    def metrics(self) -> StrategyMetrics:
        c = self._cache.stats()
        d = self._db.stats()
        return StrategyMetrics(
            strategy="cache_aside",
            cache_hits=c.hits,
            cache_misses=c.misses,
            cache_hit_rate=c.hit_rate,
            cache_size=c.size,
            db_reads=d.reads,
            db_writes=d.writes,
            writeback_pending_keys=None,
            writeback_max_pending_keys=None,
            writeback_enqueued_writes=None,
            writeback_flushed_writes=None,
            writeback_flush_errors=None,
            writeback_last_flush_ts=None,
        )


class WriteThroughStrategy(StorageStrategy):
    def __init__(self, db: SqliteDb, cache: InMemoryCache) -> None:
        self._db = db
        self._cache = cache

    def get(self, item_id: str) -> Optional[Any]:
        found, value = self._cache.get(item_id)
        if found:
            return value
        value_json = self._db.get(item_id)
        if value_json is None:
            return None
        value_obj = json.loads(value_json)
        self._cache.set(item_id, value_obj)
        return value_obj

    def set(self, item_id: str, value: Any) -> None:
        value_json = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        self._db.set(item_id, value_json)
        self._cache.set(item_id, value)

    def metrics(self) -> StrategyMetrics:
        c = self._cache.stats()
        d = self._db.stats()
        return StrategyMetrics(
            strategy="write_through",
            cache_hits=c.hits,
            cache_misses=c.misses,
            cache_hit_rate=c.hit_rate,
            cache_size=c.size,
            db_reads=d.reads,
            db_writes=d.writes,
            writeback_pending_keys=None,
            writeback_max_pending_keys=None,
            writeback_enqueued_writes=None,
            writeback_flushed_writes=None,
            writeback_flush_errors=None,
            writeback_last_flush_ts=None,
        )


class WriteBackCoordinator:
    def __init__(self, db: SqliteDb, flush_interval_ms: int, max_batch: int) -> None:
        self._db = db
        self._flush_interval_s = max(0.001, float(flush_interval_ms) / 1000.0)
        self._max_batch = max(1, int(max_batch))
        self._lock = threading.Lock()
        self._dirty: Dict[str, str] = {}
        self._enqueued_writes = 0
        self._flushed_writes = 0
        self._flush_errors = 0
        self._last_flush_ts: Optional[float] = None
        self._max_pending_keys = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="writeback-flusher", daemon=True)
        self._thread.start()

    def enqueue(self, item_id: str, value_json: str) -> None:
        with self._lock:
            self._enqueued_writes += 1
            self._dirty[item_id] = value_json
            pending = len(self._dirty)
            if pending > self._max_pending_keys:
                self._max_pending_keys = pending

    def pending_keys(self) -> int:
        with self._lock:
            return len(self._dirty)

    def snapshot(self) -> Dict[str, Optional[float]]:
        with self._lock:
            return {
                "pending_keys": len(self._dirty),
                "max_pending_keys": self._max_pending_keys,
                "enqueued_writes": self._enqueued_writes,
                "flushed_writes": self._flushed_writes,
                "flush_errors": self._flush_errors,
                "last_flush_ts": self._last_flush_ts,
            }

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._flush_interval_s)
            if self._stop.is_set():
                break
            self.flush_once()

    def flush_once(self) -> None:
        batch: Dict[str, str] = {}
        with self._lock:
            if not self._dirty:
                return
            keys = list(self._dirty.keys())[: self._max_batch]
            for k in keys:
                batch[k] = self._dirty[k]

        try:
            for item_id, value_json in batch.items():
                self._db.set(item_id, value_json)
            with self._lock:
                for k in batch.keys():
                    if k in self._dirty and self._dirty[k] == batch[k]:
                        self._dirty.pop(k, None)
                self._flushed_writes += len(batch)
                self._last_flush_ts = time.time()
        except Exception:
            with self._lock:
                self._flush_errors += 1

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        self.flush_once()


class WriteBackStrategy(StorageStrategy):
    def __init__(
        self,
        db: SqliteDb,
        cache: InMemoryCache,
        flush_interval_ms: int,
        max_batch: int,
    ) -> None:
        self._db = db
        self._cache = cache
        self._coordinator = WriteBackCoordinator(db=db, flush_interval_ms=flush_interval_ms, max_batch=max_batch)

    def get(self, item_id: str) -> Optional[Any]:
        found, value = self._cache.get(item_id)
        if found:
            return value
        value_json = self._db.get(item_id)
        if value_json is None:
            return None
        value_obj = json.loads(value_json)
        self._cache.set(item_id, value_obj)
        return value_obj

    def set(self, item_id: str, value: Any) -> None:
        value_json = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        self._cache.set(item_id, value)
        self._coordinator.enqueue(item_id, value_json)

    def metrics(self) -> StrategyMetrics:
        c = self._cache.stats()
        d = self._db.stats()
        wb = self._coordinator.snapshot()
        return StrategyMetrics(
            strategy="write_back",
            cache_hits=c.hits,
            cache_misses=c.misses,
            cache_hit_rate=c.hit_rate,
            cache_size=c.size,
            db_reads=d.reads,
            db_writes=d.writes,
            writeback_pending_keys=int(wb["pending_keys"]) if wb["pending_keys"] is not None else None,
            writeback_max_pending_keys=int(wb["max_pending_keys"]) if wb["max_pending_keys"] is not None else None,
            writeback_enqueued_writes=int(wb["enqueued_writes"]) if wb["enqueued_writes"] is not None else None,
            writeback_flushed_writes=int(wb["flushed_writes"]) if wb["flushed_writes"] is not None else None,
            writeback_flush_errors=int(wb["flush_errors"]) if wb["flush_errors"] is not None else None,
            writeback_last_flush_ts=float(wb["last_flush_ts"]) if wb["last_flush_ts"] is not None else None,
        )

    def close(self) -> None:
        self._coordinator.close()

