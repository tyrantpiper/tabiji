"""
In-Memory Security Sentinel PoC Test Suite for Trip Time Capsule Realtime & Privacy Guard
Adversarial Verification for:
1. TC-1: Broadcast payload zero-leakage invariant (Proves plaintext content/photos leak secrets over WebSocket, while desensitized metadata preserves privacy).
2. TC-2: SWR Tuple Predicate Invalidation (Proves tuple key ['/api/trips/{id}/capsules', userId] requires predicate matching).
3. TC-3: L0 LocalStorage Dual-Key Isolation (Proves tripId-only key causes cross-account contamination on shared devices, while [tripId, userId] isolates).
4. TC-4: Early Unveil Endpoint Authorization & BOLA Defense (Proves only authenticated trip members/owners can unlock early).
"""

import pytest
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


# ==============================================================================
# In-Memory Stubs & Simulation Logic under Test
# ==============================================================================

def simulate_capsule_broadcast(
    day_number: int,
    author_id: str,
    raw_content: Optional[str] = None,
    raw_photo_url: Optional[str] = None,
    desensitize: bool = True
) -> Dict[str, Any]:
    """
    Simulates the broadcast payload assembly.
    If desensitize is False (Vulnerable), plaintext content leaks across WebSocket.
    If desensitize is True (Hardened), only progress metadata is transmitted.
    """
    if not desensitize:
        # ❌ Vulnerable payload: leaks secret notes over WebSocket wire
        return {
            "event": "capsule:update",
            "day_number": day_number,
            "author_id": author_id,
            "action": "sealed",
            "content": raw_content,
            "photo_url": raw_photo_url,
        }
    else:
        # 🛡️ Hardened payload: Zero-Leakage Invariant
        return {
            "event": "capsule:update",
            "day_number": day_number,
            "author_id": author_id,
            "action": "sealed",
        }


def simulate_swr_predicate_match(key: Any, trip_id: str) -> bool:
    """
    Simulates frontend useTripRealtime SWR Tuple Predicate invalidation logic.
    Target Key shape: ['/api/trips/' + tripId + '/capsules', userId]
    """
    if ArrayPredicate := (
        isinstance(key, (list, tuple))
        and len(key) >= 1
        and isinstance(key[0], str)
        and key[0].startswith(f"/api/trips/{trip_id}/capsules")
    ):
        return True

    # Legacy string key fallback
    if isinstance(key, str) and key.startswith(f"/api/trips/{trip_id}/capsules"):
        return True

    return False


class MockLocalStorage:
    def __init__(self):
        self._store: Dict[str, str] = {}

    def set_item(self, key: str, value: str):
        self._store[key] = value

    def get_item(self, key: str) -> Optional[str]:
        return self._store.get(key)


def simulate_l0_capsule_snapshot_save(
    storage: MockLocalStorage,
    trip_id: str,
    user_id: str,
    data: Dict[str, Any],
    use_dual_key: bool = True
):
    """
    Simulates L0 storage.
    If use_dual_key is False, only trip_id is used.
    If use_dual_key is True, key is scoped by both trip_id and user_id.
    """
    key = f"tabiji_capsule_sync_{trip_id}_{user_id}" if use_dual_key else f"tabiji_capsule_sync_{trip_id}"
    storage.set_item(key, str(data))


def simulate_l0_capsule_snapshot_get(
    storage: MockLocalStorage,
    trip_id: str,
    user_id: str,
    use_dual_key: bool = True
) -> Optional[str]:
    key = f"tabiji_capsule_sync_{trip_id}_{user_id}" if use_dual_key else f"tabiji_capsule_sync_{trip_id}"
    return storage.get_item(key)


def simulate_early_unlock_authorization(
    trip: Dict[str, Any],
    requesting_user_id: str
) -> bool:
    """
    Simulates early unlock permission check.
    Only trip creator/owner or member is authorized.
    """
    is_owner = trip.get("created_by") == requesting_user_id or trip.get("user_id") == requesting_user_id
    members = trip.get("members") or []
    is_member = requesting_user_id in members
    return bool(is_owner or is_member)


# ==============================================================================
# Sentinel Test Cases
# ==============================================================================

def test_tc1_sentinel_poc_broadcast_zero_leakage_invariant():
    """
    TC-1: Verify that broadcasting raw capsule content allows wire sniffing,
    while desensitized payload completely satisfies Zero-Leakage Invariant.
    """
    secret_note = "Confession: I accidentally dropped Bob's favorite mug in the river."
    secret_photo = "https://res.cloudinary.com/tabiji/image/upload/mug.jpg"

    # 1. Vulnerable broadcast leaks plaintext secrets
    vulnerable_payload = simulate_capsule_broadcast(
        day_number=1,
        author_id="alice-uuid",
        raw_content=secret_note,
        raw_photo_url=secret_photo,
        desensitize=False
    )
    assert "content" in vulnerable_payload
    assert vulnerable_payload["content"] == secret_note
    assert vulnerable_payload["photo_url"] == secret_photo

    # 2. Hardened broadcast enforces strict Zero-Leakage Invariant
    hardened_payload = simulate_capsule_broadcast(
        day_number=1,
        author_id="alice-uuid",
        raw_content=secret_note,
        raw_photo_url=secret_photo,
        desensitize=True
    )
    assert "content" not in hardened_payload
    assert "photo_url" not in hardened_payload
    assert "mood_emoji" not in hardened_payload
    assert hardened_payload["day_number"] == 1
    assert hardened_payload["author_id"] == "alice-uuid"
    assert hardened_payload["action"] == "sealed"


def test_tc2_sentinel_poc_swr_tuple_predicate_invalidation():
    """
    TC-2: Verify that SWR key ['/api/trips/trip-101/capsules', 'user-bob']
    is properly invalidated by Tuple Predicate, while naive string match fails.
    """
    trip_id = "trip-101"
    bob_user_id = "user-bob"
    swr_key = [f"/api/trips/{trip_id}/capsules", bob_user_id]

    # Naive string equality check fails on array key
    is_naive_match = (swr_key == f"/api/trips/{trip_id}/capsules")
    assert is_naive_match is False

    # Tuple Predicate successfully matches
    assert simulate_swr_predicate_match(swr_key, trip_id) is True

    # Does not match unrelated trip
    assert simulate_swr_predicate_match(swr_key, "trip-999") is False

    # Handles legacy string key gracefully
    legacy_key = f"/api/trips/{trip_id}/capsules"
    assert simulate_swr_predicate_match(legacy_key, trip_id) is True


def test_tc3_sentinel_poc_l0_storage_cross_account_isolation():
    """
    TC-3: Verify that L0 snapshot without userId leaks Alice's unsealed memos
    to Bob on a shared device, whereas dual-key isolation blocks cross-account leak.
    """
    storage = MockLocalStorage()
    trip_id = "trip-tokyo"
    alice_id = "alice-uuid"
    bob_id = "bob-uuid"

    alice_private_data = {
        "author_id": alice_id,
        "my_entries": [{"day": 1, "note": "Secret Alice memo"}],
        "is_unlocked": False
    }

    # 1. Vulnerable: single trip_id key
    simulate_l0_capsule_snapshot_save(storage, trip_id, alice_id, alice_private_data, use_dual_key=False)
    # Bob logs in on same device and reads single-key store -> LEAK!
    bob_read_vulnerable = simulate_l0_capsule_snapshot_get(storage, trip_id, bob_id, use_dual_key=False)
    assert bob_read_vulnerable is not None
    assert "Secret Alice memo" in bob_read_vulnerable

    # 2. Hardened: dual-key scoped by trip_id AND user_id
    hardened_storage = MockLocalStorage()
    simulate_l0_capsule_snapshot_save(hardened_storage, trip_id, alice_id, alice_private_data, use_dual_key=True)
    # Bob logs in on same device and attempts to read his snapshot -> Isolated (None)
    bob_read_hardened = simulate_l0_capsule_snapshot_get(hardened_storage, trip_id, bob_id, use_dual_key=True)
    assert bob_read_hardened is None

    # Alice reads her own snapshot -> Success
    alice_read_hardened = simulate_l0_capsule_snapshot_get(hardened_storage, trip_id, alice_id, use_dual_key=True)
    assert alice_read_hardened is not None
    assert "Secret Alice memo" in alice_read_hardened


def test_tc4_sentinel_poc_early_unlock_authorization():
    """
    TC-4: Verify BOLA defense on early unlock ceremony:
    Owner and trip members can trigger unlock; external attackers are forbidden.
    """
    mock_trip = {
        "id": "trip-kyoto",
        "user_id": "creator-uuid",
        "created_by": "creator-uuid",
        "members": ["member-bob-uuid"],
        "is_capsule_unlocked": False
    }

    # Creator is authorized
    assert simulate_early_unlock_authorization(mock_trip, "creator-uuid") is True

    # Member is authorized
    assert simulate_early_unlock_authorization(mock_trip, "member-bob-uuid") is True

    # Attacker (non-member) is rejected (BOLA defense)
    assert simulate_early_unlock_authorization(mock_trip, "attacker-charlie-uuid") is False
