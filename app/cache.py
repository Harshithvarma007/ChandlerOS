"""Generic in-memory TTL cache — Section 25 of the blueprint.

Backs both the Retrieval cache and the Response cache. In-memory only, same
deferral as every other Phase 3+ module: the real backing store (Workers KV)
is a deployment binding (Phase 11), not this module's job — the eviction/
TTL/invalidation *logic* here is what would run against that store.

Safety is enforced by the caller (ask.py), not this module: "when caching
is safe" (Section 25) is a decision about *what to cache and under what
key*, which only the caller has enough context to make correctly.
"""
import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store = OrderedDict()  # key -> (value, expires_at)
        self.hits = 0
        self.misses = 0

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return value

    def set(self, key, value):
        if key in self._store:
            del self._store[key]
        elif len(self._store) >= self.max_entries:
            self._store.popitem(last=False)  # evict oldest
        self._store[key] = (value, time.monotonic() + self.ttl_seconds)

    def invalidate_all(self):
        self._store.clear()

    def stats(self):
        total = self.hits + self.misses
        return {
            "size": len(self._store), "hits": self.hits, "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }
