"""Per-trip async locking utilities to serialize read-modify-write JSONB updates."""

import asyncio
import weakref
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import AsyncIterator

MAX_TRIP_LOCKS = 2048
_LOOP_LOCKS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, OrderedDict[str, asyncio.Lock]]" = (
    weakref.WeakKeyDictionary()
)
_FALLBACK_LOCKS: "OrderedDict[str, asyncio.Lock]" = OrderedDict()


def get_trip_lock(trip_id: str) -> asyncio.Lock:
    """Return an event-loop-scoped asyncio.Lock for the specified trip_id with bounded LRU eviction."""
    try:
        loop = asyncio.get_running_loop()
        bucket = _LOOP_LOCKS.get(loop)
        if bucket is None:
            bucket = OrderedDict()
            _LOOP_LOCKS[loop] = bucket
    except RuntimeError:
        bucket = _FALLBACK_LOCKS

    key = str(trip_id)
    lock = bucket.get(key)
    if lock is None:
        lock = asyncio.Lock()
        bucket[key] = lock
    else:
        bucket.move_to_end(key)

    if len(bucket) > MAX_TRIP_LOCKS:
        for evict_key in list(bucket.keys()):
            if evict_key == key:
                continue
            cand = bucket[evict_key]
            if not cand.locked():
                bucket.pop(evict_key, None)
            if len(bucket) <= MAX_TRIP_LOCKS:
                break

    return lock


@asynccontextmanager
async def trip_lock(trip_id: str) -> AsyncIterator[None]:
    """Async context manager serializing critical sections per trip_id."""
    lock = get_trip_lock(trip_id)
    async with lock:
        yield


def __reset_locks_for_testing() -> None:
    """Reset module-level lock registries between tests."""
    _LOOP_LOCKS.clear()
    _FALLBACK_LOCKS.clear()
