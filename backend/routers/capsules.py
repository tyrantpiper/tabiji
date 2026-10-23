"""
Capsules Router
----------------
Handles Trip Time Capsule (Sealed Blind Journal & Unveiling Ceremony) endpoints:
- GET /api/trips/{trip_id}/capsules: Retrieve my capsule and collaborator progress (sealed) or all entries (unlocked)
- POST /api/trips/{trip_id}/capsules: Submit/update daily capsule entry (frozen once unlocked)
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, field_validator
from supabase import Client

from utils.deps import get_supabase, get_verified_user
from services.temporal_service import infer_destination_timezone, safe_get_zoneinfo

router = APIRouter(prefix="/api/trips", tags=["capsules"])

# ==============================================================================
# Pydantic Models & Validators
# ==============================================================================

class CapsuleCreateRequest(BaseModel):
    day_number: int # 0: overall trip finale, 1..N: daily capsule
    mood_emoji: str
    content: str
    photo_url: Optional[str] = None

    @field_validator("mood_emoji")
    def validate_mood_emoji(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed or len(trimmed) > 16:
            raise ValueError("Mood emoji must be between 1 and 16 characters")
        return trimmed

    @field_validator("content")
    def validate_content_length(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("Capsule content cannot exceed 500 characters")
        return v

    @field_validator("photo_url")
    def validate_photo_url_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        parsed = urlparse(str(v))
        if parsed.scheme != "https":
            raise ValueError("Only secure HTTPS URLs are permitted")
        if parsed.hostname != "res.cloudinary.com":
            raise ValueError("Only https://res.cloudinary.com URLs are permitted for capsule photos")
        return str(v)


class CapsuleEntryResponse(BaseModel):
    id: str
    trip_id: str
    day_number: int
    author_id: str
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None
    mood_emoji: Optional[str] = None
    content: Optional[str] = None
    photo_url: Optional[str] = None
    is_sealed: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CapsuleProgressSummary(BaseModel):
    trip_id: str
    is_unlocked: bool
    total_members: int
    submitted_members_count: int
    has_current_user_submitted: bool
    my_entries: List[CapsuleEntryResponse] = []
    revealed_entries: List[CapsuleEntryResponse] = []


# ==============================================================================
# Helper Utilities
# ==============================================================================

def check_trip_membership(trip: dict, user_id: str, supabase: Optional[Client] = None) -> bool:
    """Verifies whether user_id is trip creator/owner or in trip_members list."""
    if trip.get("created_by") in [user_id, "SYSTEM"] or trip.get("user_id") == user_id:
        return True
    if trip.get("status") == "public":
        return True
    members = trip.get("members") or []
    if isinstance(members, list) and user_id in members:
        return True
    collaborators = trip.get("collaborators") or []
    if isinstance(collaborators, list) and any(c.get("user_id") == user_id for c in collaborators if isinstance(c, dict)):
        return True
    if supabase and trip.get("id"):
        try:
            m_res = supabase.table("trip_members").select("user_id").eq("itinerary_id", trip.get("id")).eq("user_id", user_id).execute()
            if m_res and isinstance(m_res.data, list) and len(m_res.data) > 0:
                return True
        except Exception:
            pass
    return False


def compute_trip_local_bounds(trip: dict) -> tuple[datetime, datetime]:
    """
    依據行程目的地真實 IANA 時區，計算最後一天的本地 [00:00:00, 23:59:59] 並精確轉為 UTC 時間戳。
    支援全球夏令時間 (DST) 自動補償，查無時區時安全回退至 Asia/Tokyo。
    """
    end_date_str = trip.get("end_date") or trip.get("start_date")
    if not end_date_str:
        return datetime.max.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)

    dest_tz_name = trip.get("timezone") or infer_destination_timezone(trip, client_tz_str="Asia/Tokyo")
    dest_tz = safe_get_zoneinfo(dest_tz_name, fallback="Asia/Tokyo")

    try:
        parts = [int(p) for p in str(end_date_str).split("-")[:3]]
        last_day_start_local = datetime(parts[0], parts[1], parts[2], 0, 0, 0, tzinfo=dest_tz)
        trip_end_local = datetime(parts[0], parts[1], parts[2], 23, 59, 59, tzinfo=dest_tz)
        return last_day_start_local.astimezone(timezone.utc), trip_end_local.astimezone(timezone.utc)
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)


def compute_trip_end_utc(trip: dict) -> datetime:
    """相容性包裝：取得目的地最後一天 23:59:59 之 UTC 時間戳"""
    _, end_utc = compute_trip_local_bounds(trip)
    return end_utc


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.get("/{trip_id}/capsules", response_model=CapsuleProgressSummary)
async def get_trip_capsules(
    trip_id: str,
    day: Optional[int] = None,
    user_id: str = Depends(get_verified_user),
    supabase: Client = Depends(get_supabase)
):
    """
    Retrieve capsules for a trip.
    During trip: returns user's own entries + aggregated member completion status (others redacted).
    After trip: returns all unsealed entries.
    """
    # 1. Fetch trip from itineraries table and verify membership
    trip_res = supabase.table("itineraries").select("*").eq("id", trip_id).execute()
    if not trip_res.data:
        raise HTTPException(status_code=404, detail="Trip not found")
    trip = trip_res.data[0]

    if not check_trip_membership(trip, user_id, supabase):
        raise HTTPException(status_code=403, detail="Not authorized to access capsules for this trip")

    # 1.1 Check if this is a sample/demo trip (isolated single-player onboarding trip)
    is_sample = (trip.get("created_by") == "SYSTEM") or bool((trip.get("content") or {}).get("is_sample"))
    if is_sample:
        return CapsuleProgressSummary(
            trip_id=trip_id,
            is_unlocked=False,
            total_members=1,
            submitted_members_count=0,
            has_current_user_submitted=False,
            my_entries=[],
            revealed_entries=[]
        )

    # 2. Determine time-lock status
    trip_end_utc = compute_trip_end_utc(trip)
    now_utc = datetime.now(timezone.utc)
    time_reached = (now_utc >= trip_end_utc)
    is_unlocked = bool(trip.get("is_capsule_unlocked", False) or time_reached)

    # If time reached but flag not updated, atomically set is_capsule_unlocked = True
    if time_reached and not trip.get("is_capsule_unlocked", False):
        try:
            supabase.table("itineraries").update({"is_capsule_unlocked": True}).eq("id", trip_id).execute()
            is_unlocked = True
        except Exception as e:
            print(f"⚠️ Failed to set is_capsule_unlocked flag: {e}")

    # 3. Query all capsule entries for this trip
    query = supabase.table("trip_capsule_entries").select("*").eq("trip_id", trip_id)
    if day is not None:
        query = query.eq("day_number", day)
    entries_res = query.execute()
    raw_entries = entries_res.data or []

    # 4. Batch real-name profile hydration (O(1) memory map, Zero N+1 query)
    author_uuids = list(set([str(e["author_id"]) for e in raw_entries if e.get("author_id")]))
    user_profile_map: Dict[str, Dict[str, Optional[str]]] = {}

    if author_uuids:
        try:
            # 優先從 public.users 提取全域 profile
            u_res = supabase.table("users").select("id, name, avatar_url").in_("id", author_uuids).execute()
            if u_res and u_res.data:
                for u in u_res.data:
                    user_profile_map[str(u["id"])] = {
                        "name": u.get("name") or "Traveler",
                        "avatar_url": u.get("avatar_url")
                    }
        except Exception as err:
            print(f"⚠️ Failed to batch-query public.users: {err}")

        try:
            # 次級提取 trip_members 自訂頭像與名稱補充
            m_res = supabase.table("trip_members").select("user_id, user_name, user_avatar")\
                .eq("itinerary_id", trip_id).in_("user_id", author_uuids).execute()
            if m_res and m_res.data:
                for m in m_res.data:
                    uid = str(m.get("user_id"))
                    if uid not in user_profile_map:
                        user_profile_map[uid] = {
                            "name": m.get("user_name") or "Traveler",
                            "avatar_url": m.get("user_avatar")
                        }
                    else:
                        if m.get("user_name"):
                            user_profile_map[uid]["name"] = m["user_name"]
                        if m.get("user_avatar"):
                            user_profile_map[uid]["avatar_url"] = m["user_avatar"]
        except Exception as err:
            print(f"⚠️ Failed to batch-query trip_members: {err}")

    # 5. Compute members & progress
    members = list(set([trip.get("user_id")] + (trip.get("members") or [])))
    total_members = max(1, len(members))
    
    # Submissions in target scope
    submitted_user_ids = set(str(e["author_id"]) for e in raw_entries if (day is None or e.get("day_number") == day))
    submitted_count = len(submitted_user_ids)
    has_my_sub = (user_id in submitted_user_ids)

    my_entries: List[CapsuleEntryResponse] = []
    revealed_entries: List[CapsuleEntryResponse] = []

    for entry in raw_entries:
        author_id_str = str(entry["author_id"])
        is_author = (author_id_str == user_id)
        profile = user_profile_map.get(author_id_str, {})
        resolved_name = profile.get("name") or entry.get("author_name") or ("You" if is_author else "Traveler")
        resolved_avatar = profile.get("avatar_url")

        if is_author:
            my_entries.append(CapsuleEntryResponse(
                id=str(entry["id"]),
                trip_id=str(entry["trip_id"]),
                day_number=entry["day_number"],
                author_id=author_id_str,
                author_name=resolved_name,
                author_avatar=resolved_avatar,
                mood_emoji=entry.get("mood_emoji"),
                content=entry.get("content"),
                photo_url=entry.get("photo_url"),
                is_sealed=not is_unlocked,
                created_at=entry.get("created_at"),
                updated_at=entry.get("updated_at")
            ))

        if is_unlocked:
            # Fully revealed
            revealed_entries.append(CapsuleEntryResponse(
                id=str(entry["id"]),
                trip_id=str(entry["trip_id"]),
                day_number=entry["day_number"],
                author_id=author_id_str,
                author_name=resolved_name,
                author_avatar=resolved_avatar,
                mood_emoji=entry.get("mood_emoji"),
                content=entry.get("content"),
                photo_url=entry.get("photo_url"),
                is_sealed=False,
                created_at=entry.get("created_at"),
                updated_at=entry.get("updated_at")
            ))
        elif not is_author:
            # Redacted view for collaborator during trip (only metadata for progress)
            revealed_entries.append(CapsuleEntryResponse(
                id=str(entry["id"]),
                trip_id=str(entry["trip_id"]),
                day_number=entry["day_number"],
                author_id=author_id_str,
                author_name=resolved_name,
                author_avatar=resolved_avatar,
                mood_emoji=None,
                content=None,
                photo_url=None,
                is_sealed=True,
                created_at=entry.get("created_at"),
                updated_at=entry.get("updated_at")
            ))

    return CapsuleProgressSummary(
        trip_id=trip_id,
        is_unlocked=is_unlocked,
        total_members=total_members,
        submitted_members_count=submitted_count,
        has_current_user_submitted=has_my_sub,
        my_entries=my_entries,
        revealed_entries=revealed_entries
    )


@router.post("/{trip_id}/capsules", response_model=CapsuleEntryResponse)
async def submit_trip_capsule(
    trip_id: str,
    payload: CapsuleCreateRequest,
    user_id: str = Depends(get_verified_user),
    supabase: Client = Depends(get_supabase)
):
    """
    Submit or update a capsule entry for day_number (1..N or 0 for finale).
    Strictly locked once trip is completed (403 Forbidden).
    """
    # 1. Fetch trip from itineraries table and check membership
    trip_res = supabase.table("itineraries").select("*").eq("id", trip_id).execute()
    if not trip_res.data:
        raise HTTPException(status_code=404, detail="Trip not found")
    trip = trip_res.data[0]

    if not check_trip_membership(trip, user_id, supabase):
        raise HTTPException(status_code=403, detail="Not authorized to submit capsule for this trip")

    # 1.1 Sample trip check: demo itineraries cannot store collaborative time capsules
    is_sample = (trip.get("created_by") == "SYSTEM") or bool((trip.get("content") or {}).get("is_sample"))
    if is_sample:
        raise HTTPException(
            status_code=400,
            detail="Sample/demo trip does not support collaborative time capsules. Please create a custom trip and invite companions."
        )

    # 2. Check if trip is already unlocked/ended (Freezes edits upon unlock)
    _, trip_end_utc = compute_trip_local_bounds(trip)
    now_utc = datetime.now(timezone.utc)
    # 當地行程結束日 23:59:59 過去後，全面物理凍結 (Hard Freeze)
    if now_utc >= trip_end_utc:
        raise HTTPException(status_code=403, detail="旅程已結束，時光膠囊已全面封存凍結 (Modifications are frozen)，無法再新增或修改。")

    # 🛡️ 防篡改軟解鎖守衛 (Tamper-Proof Soft Unlock)：已解鎖狀態下禁止修改已存在條目，僅允許未填者補填
    if bool(trip.get("is_capsule_unlocked", False)):
        existing_res = supabase.table("trip_capsule_entries")\
            .select("id")\
            .eq("trip_id", trip_id)\
            .eq("day_number", payload.day_number)\
            .eq("author_id", user_id)\
            .execute()
        if existing_res.data and len(existing_res.data) > 0:
            raise HTTPException(
                status_code=403,
                detail="時光膠囊已提前破印揭曉。為防止偷看他人心得後篡改，已揭曉之條目嚴禁修改。"
            )

    # 3. Upsert entry into trip_capsule_entries
    entry_data = {
        "trip_id": trip_id,
        "day_number": payload.day_number,
        "author_id": user_id,
        "mood_emoji": payload.mood_emoji,
        "content": payload.content,
        "photo_url": payload.photo_url,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    upsert_res = supabase.table("trip_capsule_entries").upsert(
        entry_data,
        on_conflict="trip_id,day_number,author_id"
    ).execute()

    if not upsert_res.data:
        raise HTTPException(status_code=500, detail="Failed to save capsule entry")

    saved = upsert_res.data[0]
    return CapsuleEntryResponse(
        id=str(saved["id"]),
        trip_id=str(saved["trip_id"]),
        day_number=saved["day_number"],
        author_id=saved["author_id"],
        author_name="You",
        mood_emoji=saved["mood_emoji"],
        content=saved["content"],
        photo_url=saved.get("photo_url"),
        is_sealed=True,
        created_at=saved.get("created_at"),
        updated_at=saved.get("updated_at")
    )


@router.post("/{trip_id}/capsules/unlock", response_model=CapsuleProgressSummary)
async def unlock_trip_capsules_early(
    trip_id: str,
    user_id: str = Depends(get_verified_user),
    supabase: Client = Depends(get_supabase)
):
    """
    提前破印盛典解鎖端點（例如告別晚宴現場全員開箱）。
    權限檢查：必須為行程擁有者或成員，防禦 BOLA 越權。
    """
    trip_res = supabase.table("itineraries").select("*").eq("id", trip_id).execute()
    if not trip_res.data:
        raise HTTPException(status_code=404, detail="Trip not found")
    trip = trip_res.data[0]

    if not check_trip_membership(trip, user_id, supabase):
        raise HTTPException(status_code=403, detail="Not authorized to unlock capsules for this trip")

    # 1.1 Sample trip check
    is_sample = (trip.get("created_by") == "SYSTEM") or bool((trip.get("content") or {}).get("is_sample"))
    if is_sample:
        raise HTTPException(
            status_code=400,
            detail="Sample/demo trip does not support collaborative time capsules."
        )

    # 🛡️ 當地時區最後一天守衛 (Last-Day Gate)
    last_day_start_utc, _ = compute_trip_local_bounds(trip)
    now_utc = datetime.now(timezone.utc)
    if now_utc < last_day_start_utc:
        raise HTTPException(
            status_code=400,
            detail="提前破印盛典僅在行程最後一天（目的地當地時間）開放，旅途中途禁止提前解鎖。"
        )

    try:
        supabase.table("itineraries").update({"is_capsule_unlocked": True}).eq("id", trip_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update unlock status: {e}")

    return await get_trip_capsules(trip_id=trip_id, user_id=user_id, supabase=supabase)
