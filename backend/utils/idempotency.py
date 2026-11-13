"""Bounded in-memory Idempotency-Key deduplication cache for offline sync replays."""

import copy
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple

DEFAULT_TTL_SECONDS = 300.0
MAX_IDEMPOTENCY_ENTRIES = 1024
_IDEMPOTENCY_STORE: "OrderedDict[Tuple[str, str, str], Tuple[float, Any]]" = OrderedDict()


def _prune_expired(now: float) -> None:
    expired = [k for k, (expires_at, _) in _IDEMPOTENCY_STORE.items() if expires_at <= now]
    for k in expired:
        _IDEMPOTENCY_STORE.pop(k, None)


def get_idempotent_response(scope: str, user_id: str, key: Optional[str]) -> Optional[Any]:
    """Return a deep copy of a cached response if a fresh Idempotency-Key exists."""
    if not key or not key.strip():
        return None
    now = time.monotonic()
    _prune_expired(now)
    cache_key = (scope, str(user_id), key.strip())
    entry = _IDEMPOTENCY_STORE.get(cache_key)
    if entry is None:
        return None
    expires_at, payload = entry
    if expires_at <= now:
        _IDEMPOTENCY_STORE.pop(cache_key, None)
        return None
    _IDEMPOTENCY_STORE.move_to_end(cache_key)
    return copy.deepcopy(payload)


def store_idempotent_response(
    scope: str,
    user_id: str,
    key: Optional[str],
    payload: Any,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> None:
    """Cache a successful mutation response under the bounded LRU+TTL store."""
    if not key or not key.strip():
        return
    now = time.monotonic()
    _prune_expired(now)
    cache_key = (scope, str(user_id), key.strip())
    _IDEMPOTENCY_STORE[cache_key] = (now + ttl_seconds, copy.deepcopy(payload))
    _IDEMPOTENCY_STORE.move_to_end(cache_key)
    while len(_IDEMPOTENCY_STORE) > MAX_IDEMPOTENCY_ENTRIES:
        _IDEMPOTENCY_STORE.popitem(last=False)


def __reset_idempotency_cache_for_testing() -> None:
    """Clear idempotency cache between tests."""
    _IDEMPOTENCY_STORE.clear()
