"""
In-Memory Security Sentinel PoC: Capsules Temporal & Anti-Tampering Verification
Adversarial Verification for:
1. TC-1: Destination Timezone Accuracy vs Hardcoded Tokyo Drift (13hr drift prevention).
2. TC-2: Last-Day Early Unveil Guard (Premature unlock rejection on Day 1/2).
3. TC-3: Anti-Tampering Soft Unlock (Rejects editing revealed entries, permits catch-up for unsubmitted).
4. TC-4: Local Midnight Hard Freeze (Rejects all submissions after destination 23:59:59).
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from backend.services.temporal_service import infer_destination_timezone, safe_get_zoneinfo


# ==============================================================================
# Simulation Logic Under Test
# ==============================================================================

def compute_trip_local_bounds(trip: dict) -> tuple[datetime, datetime]:
    """
    Computes [last_day_start_utc, trip_end_utc] anchored to destination local time.
    """
    end_date_str = trip.get("end_date") or trip.get("start_date")
    if not end_date_str:
        return datetime.max.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)

    dest_tz_name = trip.get("timezone") or infer_destination_timezone(trip, client_tz_str="Asia/Tokyo")
    dest_tz = safe_get_zoneinfo(dest_tz_name, fallback="Asia/Tokyo")

    try:
        parts = [int(p) for p in str(end_date_str).split("-")[:3]]
        # 00:00:00 destination local time
        last_day_start_local = datetime(parts[0], parts[1], parts[2], 0, 0, 0, tzinfo=dest_tz)
        # 23:59:59 destination local time
        trip_end_local = datetime(parts[0], parts[1], parts[2], 23, 59, 59, tzinfo=dest_tz)

        return last_day_start_local.astimezone(timezone.utc), trip_end_local.astimezone(timezone.utc)
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)


def legacy_compute_trip_end_utc(trip: dict) -> datetime:
    """Legacy buggy implementation hardcoded to Tokyo UTC+9."""
    end_date_str = trip.get("end_date") or trip.get("start_date")
    if not end_date_str:
        return datetime.max.replace(tzinfo=timezone.utc)
    parts = [int(p) for p in str(end_date_str).split("-")[:3]]
    return datetime(parts[0], parts[1], parts[2], 14, 59, 59, tzinfo=timezone.utc)


def simulate_unlock_gate(trip: dict, now_utc: datetime) -> tuple[int, str]:
    """Simulates last-day unlock guard."""
    last_day_start_utc, _ = compute_trip_local_bounds(trip)
    if now_utc < last_day_start_utc:
        return 400, "提前破印盛典僅在行程最後一天（目的地當地時間）開放，旅途中途禁止提前解鎖。"
    return 200, "OK"


class MockCapsuleStore:
    def __init__(self):
        self.entries: Dict[str, Dict[str, Any]] = {}

    def has_entry(self, trip_id: str, day_number: int, author_id: str) -> bool:
        key = f"{trip_id}:{day_number}:{author_id}"
        return key in self.entries

    def save_entry(self, trip_id: str, day_number: int, author_id: str, content: str, is_sealed: bool):
        key = f"{trip_id}:{day_number}:{author_id}"
        self.entries[key] = {
            "trip_id": trip_id,
            "day_number": day_number,
            "author_id": author_id,
            "content": content,
            "is_sealed": is_sealed
        }


def simulate_submit_capsule(
    store: MockCapsuleStore,
    trip: dict,
    day_number: int,
    author_id: str,
    content: str,
    now_utc: datetime,
    is_trip_unlocked: bool
) -> tuple[int, str]:
    """Simulates submit_trip_capsule with anti-tampering soft unlock defense."""
    _, trip_end_utc = compute_trip_local_bounds(trip)

    # 1. Local Midnight Hard Freeze
    if now_utc >= trip_end_utc:
        return 403, "旅程已結束，時光膠囊已全面封存凍結，無法再新增或修改。"

    # 2. Tamper-Proof Soft Unlock
    if is_trip_unlocked:
        if store.has_entry(trip.get("id", ""), day_number, author_id):
            return 403, "時光膠囊已提前破印揭曉。為防止偷看他人心得後篡改，已揭曉之條目嚴禁修改。"

    # 3. Save entry (revealed if already unlocked, sealed otherwise)
    store.save_entry(trip.get("id", ""), day_number, author_id, content, is_sealed=not is_trip_unlocked)
    return 200, "OK"


# ==============================================================================
# Sentinel Test Cases
# ==============================================================================

def test_tc1_sentinel_poc_destination_timezone_accuracy():
    """
    TC-1: Verify that New York trip end date is computed as 23:59:59 EDT (03:59:59 UTC next day),
    demonstrating that legacy hardcoded Tokyo UTC+9 was 13 hours prematurely drifted!
    """
    ny_trip = {
        "id": "trip-ny-01",
        "title": "曼哈頓秋日探險",
        "destination": "New York",
        "dest_city": "New York",
        "dest_country": "USA",
        "end_date": "2026-10-23"
    }

    # 1. Legacy Tokyo calculation
    legacy_end_utc = legacy_compute_trip_end_utc(ny_trip)
    assert legacy_end_utc == datetime(2026, 10, 23, 14, 59, 59, tzinfo=timezone.utc)
    # In New York (EDT, UTC-4), 14:59:59 UTC is 10:59:59 AM in the MORNING!
    ny_tz = safe_get_zoneinfo("America/New_York")
    legacy_local = legacy_end_utc.astimezone(ny_tz)
    assert legacy_local.hour == 10  # ❌ Bug: frozen at 10 AM!

    # 2. Hardened Destination Timezone calculation
    start_utc, end_utc = compute_trip_local_bounds(ny_trip)
    end_local = end_utc.astimezone(ny_tz)
    assert end_local.year == 2026
    assert end_local.month == 10
    assert end_local.day == 23
    assert end_local.hour == 23
    assert end_local.minute == 59
    assert end_local.second == 59
    # In UTC, 23:59:59 EDT is 03:59:59 UTC on 10-24
    assert end_utc == datetime(2026, 10, 24, 3, 59, 59, tzinfo=timezone.utc)


def test_tc2_sentinel_poc_last_day_early_unlock_guard():
    """
    TC-2: Verify that early unlock is rejected on Day 1 or Day 2,
    and only accepted once destination local time reaches the final day.
    """
    trip = {
        "id": "trip-london-01",
        "title": "倫敦大笨鐘漫步",
        "destination": "London",
        "dest_city": "London",
        "end_date": "2026-10-23"
    }
    london_tz = safe_get_zoneinfo("Europe/London")

    # Day 1: 2026-10-21 14:00 London time -> Must be rejected (400)
    day1_time = datetime(2026, 10, 21, 14, 0, 0, tzinfo=london_tz).astimezone(timezone.utc)
    code, msg = simulate_unlock_gate(trip, day1_time)
    assert code == 400
    assert "提前破印盛典僅在行程最後一天" in msg

    # Final day evening: 2026-10-23 20:30 London time -> Accepted (200)
    last_day_evening = datetime(2026, 10, 23, 20, 30, 0, tzinfo=london_tz).astimezone(timezone.utc)
    code, msg = simulate_unlock_gate(trip, last_day_evening)
    assert code == 200
    assert msg == "OK"


def test_tc3_sentinel_poc_anti_tampering_soft_unlock():
    """
    TC-3: Verify Anti-Tampering invariant:
    Once early unlocked, Alice (who already submitted) CANNOT tamper with her entry (403),
    while Bob (who has not submitted) CAN catch-up submit before midnight (200).
    """
    store = MockCapsuleStore()
    trip = {
        "id": "trip-kyoto-01",
        "title": "京都紅葉之行",
        "destination": "Kyoto",
        "end_date": "2026-10-23"
    }
    tokyo_tz = safe_get_zoneinfo("Asia/Tokyo")

    # 1. Alice submitted Day 1 before unlock
    store.save_entry("trip-kyoto-01", 1, "alice", "Alice original secret memo", is_sealed=True)

    # 2. At 21:00, early unlock happens
    now_evening = datetime(2026, 10, 23, 21, 0, 0, tzinfo=tokyo_tz).astimezone(timezone.utc)

    # 3. Alice attempts to edit her memo after unlock -> 403 Forbidden!
    code_alice, msg_alice = simulate_submit_capsule(
        store, trip, day_number=1, author_id="alice",
        content="Alice changed memo after reading Bob",
        now_utc=now_evening, is_trip_unlocked=True
    )
    assert code_alice == 403
    assert "已揭曉之條目嚴禁修改" in msg_alice
    # Content remains untampered
    assert store.entries["trip-kyoto-01:1:alice"]["content"] == "Alice original secret memo"

    # 4. Bob has NOT submitted yet -> Catch-up submission is ALLOWED (200)!
    code_bob, msg_bob = simulate_submit_capsule(
        store, trip, day_number=1, author_id="bob",
        content="Bob catch-up memo at hotel",
        now_utc=now_evening, is_trip_unlocked=True
    )
    assert code_bob == 200
    assert store.has_entry("trip-kyoto-01", 1, "bob") is True
    # Saved directly as unsealed
    assert store.entries["trip-kyoto-01:1:bob"]["is_sealed"] is False


def test_tc4_sentinel_poc_destination_midnight_hard_freeze():
    """
    TC-4: Verify that once destination local midnight passes (e.g. 00:05 AM next day),
    ALL writes (new catch-up or edits) are completely frozen (403).
    """
    store = MockCapsuleStore()
    trip = {
        "id": "trip-kyoto-01",
        "title": "京都紅葉之行",
        "destination": "Kyoto",
        "end_date": "2026-10-23"
    }
    tokyo_tz = safe_get_zoneinfo("Asia/Tokyo")

    # 00:05 AM on 10-24 (past 23:59:59 10-23)
    post_midnight = datetime(2026, 10, 24, 0, 5, 0, tzinfo=tokyo_tz).astimezone(timezone.utc)

    code, msg = simulate_submit_capsule(
        store, trip, day_number=1, author_id="charlie",
        content="Late submission after midnight",
        now_utc=post_midnight, is_trip_unlocked=True
    )
    assert code == 403
    assert "時光膠囊已全面封存凍結" in msg
