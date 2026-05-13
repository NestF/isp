import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    sets: int
    deletes: int
    size: int

    @property
    def hit_rate(self) -> float:
        denom = self.hits + self.misses
        if denom <= 0:
            return 0.0
        return self.hits / denom


class InMemoryCache:
    def __init__(self, ttl_seconds: Optional[float] = None) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._items: Dict[str, Tuple[float, Any]] = {}
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._deletes = 0

    def get(self, key: str) -> Tuple[bool, Any]:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self._misses += 1
                return False, None

            expires_at, value = item
            if expires_at != 0.0 and now >= expires_at:
                self._items.pop(key, None)
                self._misses += 1
                return False, None

            self._hits += 1
            return True, value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            expires_at = 0.0
            if self._ttl_seconds is not None:
                expires_at = time.monotonic() + float(self._ttl_seconds)
            self._items[key] = (expires_at, value)
            self._sets += 1

    def delete(self, key: str) -> None:
        with self._lock:
            removed = self._items.pop(key, None)
            if removed is not None:
                self._deletes += 1

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                sets=self._sets,
                deletes=self._deletes,
                size=len(self._items),
            )

