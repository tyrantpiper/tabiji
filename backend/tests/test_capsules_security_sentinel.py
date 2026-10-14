"""
In-Memory Security Sentinel PoC Test Suite for Trip Time Capsule
Adversarial Verification for:
1. BOLA / IDOR leak prevention prior to unlock
2. Time-lock integrity against clock spoofing
3. Cloudinary domain whitelist & SSRF defense
"""

import pytest
from pydantic import BaseModel, HttpUrl, ValidationError, field_validator
from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import urlparse

# ==============================================================================
# Model Definitions under Test
# ==============================================================================

class CapsuleEntryCreate(BaseModel):
    trip_id: str
    day_number: int
    mood_emoji: str
    content: str
    photo_url: Optional[str] = None

    @field_validator("mood_emoji")
    def validate_mood_emoji(cls, v):
        if not v or len(v) > 8:
            raise ValueError("Mood emoji must be between 1 and 8 characters")
        return v

    @field_validator("content")
    def validate_content_length(cls, v):
        if len(v) > 500:
            raise ValueError("Capsule content cannot exceed 500 characters")
        return v

    @field_validator("photo_url")
    def validate_photo_url_domain(cls, v):
        if v is None:
            return v
        parsed = urlparse(str(v))
        if parsed.scheme != "https":
            raise ValueError("Only secure HTTPS URLs are permitted")
        if parsed.hostname != "res.cloudinary.com":
            raise ValueError("Only https://res.cloudinary.com URLs are permitted")
        return v


class CapsuleEntryProjection(BaseModel):
    id: str
    trip_id: str
    day_number: int
    author_id: str
    mood_emoji: Optional[str]
    content: Optional[str]
    photo_url: Optional[str]
    is_sealed: bool


def project_capsule_for_viewer(
    raw_entry: dict, 
    viewer_id: str, 
    is_trip_unlocked: bool,
    trip_end_date_utc: datetime,
    current_time_utc: datetime
) -> CapsuleEntryProjection:
    """
    Simulates the backend projection logic enforcing confidential redaction.
    """
    is_author = (raw_entry["author_id"] == viewer_id)
    time_reached = (current_time_utc >= trip_end_date_utc)
    can_reveal = is_trip_unlocked and time_reached

    if is_author or can_reveal:
        # Full view
        return CapsuleEntryProjection(
            id=raw_entry["id"],
            trip_id=raw_entry["trip_id"],
            day_number=raw_entry["day_number"],
            author_id=raw_entry["author_id"],
            mood_emoji=raw_entry["mood_emoji"],
            content=raw_entry["content"],
            photo_url=raw_entry.get("photo_url"),
            is_sealed=not can_reveal
        )
    else:
        # Redacted view for collaborator during trip
        return CapsuleEntryProjection(
            id=raw_entry["id"],
            trip_id=raw_entry["trip_id"],
            day_number=raw_entry["day_number"],
            author_id=raw_entry["author_id"],
            mood_emoji=None,
            content=None,
            photo_url=None,
            is_sealed=True
        )


# ==============================================================================
# Sentinel Adversarial PoC Tests
# ==============================================================================

def test_sentinel_poc_bola_leak_prevention_during_trip():
    """
    Adversarial Vector: Collaborator attempts to peek into another traveler's
    unrevealed capsule entry prior to trip unlock.
    """
    raw_alice_entry = {
        "id": "entry-1",
        "trip_id": "trip-tokyo",
        "day_number": 1,
        "author_id": "alice",
        "mood_emoji": "🤫",
        "content": "Secret note: I bought a gift for Bob today!",
        "photo_url": "https://res.cloudinary.com/tabiji/image/upload/gift.webp"
    }

    trip_end = datetime(2026, 10, 18, 14, 59, 59, tzinfo=timezone.utc)
    current_time = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc) # Trip ongoing

    # Bob views Alice's entry
    bob_view = project_capsule_for_viewer(
        raw_alice_entry,
        viewer_id="bob",
        is_trip_unlocked=False,
        trip_end_date_utc=trip_end,
        current_time_utc=current_time
    )

    # ASSERTION: Content and photo must be completely redacted for Bob
    assert bob_view.content is None
    assert bob_view.photo_url is None
    assert bob_view.mood_emoji is None
    assert bob_view.is_sealed is True

    # ASSERTION: Alice viewing her own entry retains full visibility
    alice_view = project_capsule_for_viewer(
        raw_alice_entry,
        viewer_id="alice",
        is_trip_unlocked=False,
        trip_end_date_utc=trip_end,
        current_time_utc=current_time
    )
    assert alice_view.content == "Secret note: I bought a gift for Bob today!"
    assert alice_view.photo_url == "https://res.cloudinary.com/tabiji/image/upload/gift.webp"
    assert alice_view.mood_emoji == "🤫"


def test_sentinel_poc_time_lock_bypass_defense():
    """
    Adversarial Vector: Trip flag inadvertently set to true or client tries to claim
    it is unlocked before actual destination end_date_utc is reached.
    """
    raw_alice_entry = {
        "id": "entry-1",
        "trip_id": "trip-tokyo",
        "day_number": 1,
        "author_id": "alice",
        "mood_emoji": "🤫",
        "content": "Super secret",
        "photo_url": "https://res.cloudinary.com/tabiji/image/upload/gift.webp"
    }

    trip_end = datetime(2026, 10, 18, 14, 59, 59, tzinfo=timezone.utc)
    current_time = datetime(2026, 10, 17, 0, 0, 0, tzinfo=timezone.utc) # Not yet reached!

    # Even if is_trip_unlocked flag was mistakenly passed as True:
    view = project_capsule_for_viewer(
        raw_alice_entry,
        viewer_id="bob",
        is_trip_unlocked=True, # Malicious or desynced flag
        trip_end_date_utc=trip_end,
        current_time_utc=current_time
    )

    # Must still be protected by double-guard
    assert view.content is None
    assert view.photo_url is None
    assert view.is_sealed is True


def test_sentinel_poc_malicious_photo_url_injection_rejected():
    """
    Adversarial Vector: SSRF or XSS payload injected via photo_url.
    """
    # 1. Reject internal AWS/GCP metadata IP
    with pytest.raises(ValidationError):
        CapsuleEntryCreate(
            trip_id="trip-1",
            day_number=1,
            mood_emoji="✨",
            content="Hello",
            photo_url="http://169.254.169.254/latest/meta-data/"
        )

    # 2. Reject arbitrary non-Cloudinary external domain
    with pytest.raises(ValidationError):
        CapsuleEntryCreate(
            trip_id="trip-1",
            day_number=1,
            mood_emoji="✨",
            content="Hello",
            photo_url="https://malicious-attacker.com/exploit.jpg"
        )

    # 3. Reject javascript protocol
    with pytest.raises(ValidationError):
        CapsuleEntryCreate(
            trip_id="trip-1",
            day_number=1,
            mood_emoji="✨",
            content="Hello",
            photo_url="javascript:alert(1)"
        )

    # 4. Accept valid Cloudinary HTTPS url
    valid_entry = CapsuleEntryCreate(
        trip_id="trip-1",
        day_number=1,
        mood_emoji="✨",
        content="Hello",
        photo_url="https://res.cloudinary.com/REDACTED_CLOUDINARY_CLOUD/image/upload/v1/capsule_polaroid.webp"
    )
    assert str(valid_entry.photo_url) == "https://res.cloudinary.com/REDACTED_CLOUDINARY_CLOUD/image/upload/v1/capsule_polaroid.webp"


def test_sentinel_poc_author_id_must_be_valid_uuid():
    """
    Adversarial Vector: Dirty non-UUID or SQL injection payload passed as author_id.
    """
    import uuid

    def validate_uuid_string(val: str) -> bool:
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, TypeError):
            return False

    # 1. Non-UUID mock string rejected
    assert validate_uuid_string("user-demo-partner-1") is False

    # 2. SQL injection payload rejected
    assert validate_uuid_string("' OR '1'='1") is False

    # 3. Standard RFC 4122 UUID accepted
    assert validate_uuid_string("66234892-200e-4a3f-98b4-dbb58dc6e3fa") is True


def test_sentinel_poc_realname_hydration_isolation():
    """
    Adversarial Vector: Batch hydration must correctly bind real traveler names
    without leaking unauthenticated or foreign user profiles.
    """
    profile_map = {
        "3f7abf22-b447-4281-b240-584549c79943": {"name": "Ryan", "avatar_url": "https://avatar.url/ryan.jpg"},
        "66234892-200e-4a3f-98b4-dbb58dc6e3fa": {"name": "Pig", "avatar_url": "https://avatar.url/pig.jpg"},
        "c14d3bc6-0540-44ec-98f8-ad649c9ee261": {"name": "Aimee", "avatar_url": "https://avatar.url/aimee.jpg"}
    }

    # Author present in profile map
    ryan_id = "3f7abf22-b447-4281-b240-584549c79943"
    ryan_name = profile_map.get(ryan_id, {}).get("name") or "Traveler"
    assert ryan_name == "Ryan"

    pig_id = "66234892-200e-4a3f-98b4-dbb58dc6e3fa"
    pig_name = profile_map.get(pig_id, {}).get("name") or "Traveler"
    assert pig_name == "Pig"

    # Author missing (e.g. unknown stranger ID) falls back gracefully
    unknown_id = "00000000-0000-0000-0000-000000000005"
    unknown_name = profile_map.get(unknown_id, {}).get("name") or "Traveler"
    assert unknown_name == "Traveler"

