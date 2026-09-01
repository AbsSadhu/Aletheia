from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _CacheEntry(Generic[V]):
    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    def __init__(self, max_size: int = 256, default_ttl_secs: float = 300.0) -> None:
        self.max_size = max_size
        self.default_ttl_secs = default_ttl_secs
        self._store: OrderedDict[K, _CacheEntry[V]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= monotonic():
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return entry.value

    def set(self, key: K, value: V, ttl_secs: float | None = None) -> V:
        with self._lock:
            expires_at = monotonic() + (ttl_secs or self.default_ttl_secs)
            self._store[key] = _CacheEntry(value=value, expires_at=expires_at)
            self._store.move_to_end(key)
            self._prune_locked()
            return value

    def invalidate(self, key: K) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def snapshot(self) -> dict[K, V]:
        with self._lock:
            now = monotonic()
            return {
                key: entry.value
                for key, entry in self._store.items()
                if entry.expires_at > now
            }

    def _prune_locked(self) -> None:
        now = monotonic()
        expired_keys = [key for key, entry in self._store.items() if entry.expires_at <= now]
        for key in expired_keys:
            self._store.pop(key, None)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)
