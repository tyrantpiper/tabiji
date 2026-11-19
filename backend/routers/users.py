"""
Users Router
------------
Handles user-related API endpoints.
Now interacts with the dedicated `public.users` table (Phase 27).
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Any, Iterable, Optional, Set, Tuple
import uuid
from datetime import datetime, timezone
import hashlib
import re
import time
from urllib.parse import quote, unquote, urlparse
import httpx
import orjson
from utils.deps import get_supabase, get_verified_user, build_supabase_rest_headers
from models.base import UpdateProfileRequest
import os
from services.geocode_service import HTTPX_CLIENT

# 🆕 Standardized prefix for user endpoints
router = APIRouter(prefix="/api/users", tags=["users"])

_SINGLE_TRANSFORM_SEGMENT_RE = re.compile(
    r"^(?:[wh]_\d+(?:\.\d+)?|c_(?:scale|fit|limit|mfit|fill|lfill|pad|lpad|mpad|fill_pad|crop|thumb|imagga_crop|imagga_scale)|q_(?:auto(?::(?:best|good|eco|low))?|\d+(?::\d+)?)|f_(?:auto|webp|avif|jpg|jpeg|png|gif|svg|pdf|mp4|webm)|dpr_(?:auto|\d+(?:\.\d+)?)|g_(?:auto(?::[a-z_]+)?|face|faces|center|north|south|east|west|north_east|north_west|south_east|south_west)|fl_[a-z0-9_.:-]+|e_[a-z0-9_.:-]+|ar_\d+(?::\d+|\.\d+)?|r_(?:max|\d+(?::\d+)*)|a_(?:-?\d+|auto_(?:right|left)|ignore|exif|hflip|vflip)|o_\d+|bo_[^,/]+|co_(?:rgb:[0-9a-fA-F]{3,8}|[a-z]+)|t_[a-zA-Z0-9_-]+|b_(?:auto(?::[a-z_]+)?|rgb:[0-9a-fA-F]{3,8}|[a-z]+))$"
)
_SAFE_PUBLIC_ID_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")
_VERSION_SEGMENT_RE = re.compile(r"^v\d+$")
_CLOUD_UPLOAD_PATH_RE = re.compile(r"^/([^/]+)/(image|video|raw)/upload/(.+)$")
_RESOURCE_UPLOAD_PATH_RE = re.compile(r"^/(image|video|raw)/upload/(.+)$")
_BARE_UPLOAD_PATH_RE = re.compile(r"^/upload/(.+)$")


def _get_cloudinary_config() -> Tuple[str, str, str]:
    cloud_name = (
        os.getenv("CLOUDINARY_CLOUD_NAME")
        or os.getenv("NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME")
        or ""
    ).strip()
    api_key = (
        os.getenv("CLOUDINARY_API_KEY")
        or os.getenv("NEXT_PUBLIC_CLOUDINARY_API_KEY")
        or ""
    ).strip()
    api_secret = (os.getenv("CLOUDINARY_API_SECRET") or "").strip()

    if not (cloud_name and api_key and api_secret):
        cloudinary_url = (os.getenv("CLOUDINARY_URL") or "").strip()
        if cloudinary_url:
            try:
                parsed = urlparse(cloudinary_url)
                if parsed.scheme == "cloudinary":
                    if not cloud_name and parsed.hostname:
                        cloud_name = unquote(parsed.hostname).strip()
                    if not api_key and parsed.username:
                        api_key = unquote(parsed.username).strip()
                    if not api_secret and parsed.password:
                        api_secret = unquote(parsed.password).strip()
            except Exception:
                pass

    return cloud_name, api_key, api_secret


def _is_safe_public_id(val: Optional[str]) -> bool:
    if not isinstance(val, str):
        return False
    trimmed = val.strip()
    if not trimmed or len(trimmed) > 256:
        return False
    if ".." in trimmed or trimmed.startswith("/") or trimmed.endswith("/") or "//" in trimmed:
        return False
    if not _SAFE_PUBLIC_ID_RE.match(trimmed):
        return False
    return not any(seg in ("", ".", "..") for seg in trimmed.split("/"))


def _is_transform_segment(seg: str) -> bool:
    return "," in seg or bool(_SINGLE_TRANSFORM_SEGMENT_RE.match(seg))


def extract_cloudinary_asset(url: Optional[str]) -> Optional[Tuple[Optional[str], str, str]]:
    """Extract (cloud_name, resource_type, public_id) from a Cloudinary upload URL."""
    if not isinstance(url, str):
        return None
    trimmed = url.strip()
    if not trimmed:
        return None
    try:
        parsed = urlparse(trimmed)
        if parsed.scheme not in ("http", "https"):
            return None
        host = (parsed.hostname or "").lower().rstrip(".")
        if host != "res.cloudinary.com" and not host.endswith(".cloudinary.com"):
            return None

        pathname = unquote(parsed.path or "")
        url_cloud: Optional[str] = None
        resource_type = "image"
        remainder: Optional[str] = None

        m = _CLOUD_UPLOAD_PATH_RE.match(pathname)
        if m:
            url_cloud, resource_type, remainder = m.group(1), m.group(2), m.group(3)
        else:
            m = _RESOURCE_UPLOAD_PATH_RE.match(pathname)
            if m:
                resource_type, remainder = m.group(1), m.group(2)
            else:
                m = _BARE_UPLOAD_PATH_RE.match(pathname)
                if m:
                    remainder = m.group(1)

        if not remainder:
            return None

        segments = [seg for seg in remainder.split("/") if seg]
        if not segments:
            return None

        version_idx = next(
            (idx for idx, seg in enumerate(segments[:-1]) if _VERSION_SEGMENT_RE.match(seg)),
            -1,
        )
        if version_idx != -1:
            segments = segments[version_idx + 1:]
        else:
            while len(segments) > 1 and _is_transform_segment(segments[0]):
                segments.pop(0)

        if not segments:
            return None
        if len(segments) == 1 and _VERSION_SEGMENT_RE.match(segments[0]):
            return None

        joined = "/".join(segments)
        public_id = joined if resource_type == "raw" else re.sub(r"\.[^./]+$", "", joined)
        if not _is_safe_public_id(public_id):
            return None
        return url_cloud, resource_type, public_id.strip()
    except Exception:
        return None


def collect_cloudinary_urls(
    rows: Any,
    fields: Tuple[str, ...] = ("photo_url", "avatar_url"),
) -> Set[str]:
    urls: Set[str] = set()
    if not isinstance(rows, list):
        return urls
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in fields:
            val = row.get(field)
            if isinstance(val, str):
                trimmed = val.strip()
                if extract_cloudinary_asset(trimmed) is not None:
                    urls.add(trimmed)
    return urls


async def destroy_cloudinary_assets(urls: Iterable[str]) -> int:
    """Best-effort Cloudinary asset deletion for backend-managed fields."""
    targets: dict[Tuple[str, str], Optional[str]] = {}
    for raw_url in urls:
        asset = extract_cloudinary_asset(raw_url)
        if asset is None:
            continue
        asset_cloud, resource_type, public_id = asset
        targets.setdefault((resource_type, public_id), asset_cloud)

    if not targets:
        return 0

    cloud_name, api_key, api_secret = _get_cloudinary_config()
    if not (cloud_name and api_key and api_secret):
        print("⚠️ [Cloudinary] Credentials not configured; skipping backend asset cleanup.")
        return 0

    filtered = [
        (resource_type, public_id)
        for (resource_type, public_id), asset_cloud in targets.items()
        if not asset_cloud or asset_cloud == cloud_name
    ]
    if not filtered:
        return 0

    destroyed = 0
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for resource_type, public_id in filtered:
                try:
                    timestamp = int(time.time())
                    sig_payload = f"invalidate=true&public_id={public_id}&timestamp={timestamp}{api_secret}"
                    signature = hashlib.sha1(sig_payload.encode("utf-8")).hexdigest()
                    endpoint = f"https://api.cloudinary.com/v1_1/{quote(cloud_name, safe='')}/{resource_type}/destroy"
                    resp = await client.post(
                        endpoint,
                        data={
                            "public_id": public_id,
                            "timestamp": str(timestamp),
                            "api_key": api_key,
                            "invalidate": "true",
                            "signature": signature,
                        },
                    )
                    if resp.is_success:
                        payload = resp.json() if resp.content else {}
                        result = payload.get("result") if isinstance(payload, dict) else None
                        if result == "ok":
                            destroyed += 1
                    else:
                        print(f"⚠️ [Cloudinary] Destroy failed for {public_id}: HTTP {resp.status_code}")
                except Exception as item_err:
                    print(f"⚠️ [Cloudinary] Destroy error for {public_id}: {item_err}")
    except Exception as client_err:
        print(f"⚠️ [Cloudinary] Cleanup client error: {client_err}")

    return destroyed

def is_valid_uuid(val: str):
    """🩺 驗證是否為有效的 UUID 格式，防止字串如 'null' 觸發 DB 錯誤"""
    if not val or val.lower() == "null" or val.lower() == "undefined":
        return False
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

@router.get("/{user_id}/profile")
async def get_user_profile(user_id: str, supabase=Depends(get_supabase)):
    """
    🔍 獲取使用者個人資料 (暱稱、頭貼)
    
    從 `public.users` 表取資料 (Single Source of Truth)
    """
    # 🛡️ Defensive Check: UUID 格式預檢
    if not is_valid_uuid(user_id):
        print(f"🚫 無效的 User ID 格式: {user_id}")
        return {
            "id": user_id,
            "nickname": "Traveler",
            "avatar_url": None,
            "error": "Invalid ID format"
        }

    try:
        print(f"🔍 正在尋找使用者 {user_id} 的資料...")
        
        # 1. 直接查詢 public.users (使用 .limit(1) 避免 PGRST116 0-row 例外)
        res = supabase.table("users").select("id, name, avatar_url, email").eq("id", user_id).limit(1).execute()

        raw_user_data = getattr(res, "data", None)
        user_row = raw_user_data[0] if isinstance(raw_user_data, list) and raw_user_data else (
            raw_user_data if isinstance(raw_user_data, dict) else None
        )
        if user_row:
            user = user_row
            nickname = user.get("name") or "Unknown Traveler"
            avatar_url = user.get("avatar_url")
            print(f"✅ 找到使用者: {nickname}")
            
            return {
                "id": user_id,
                "name": nickname,
                "avatar_url": avatar_url
            }
            
        # 2. 如果找不到 (可能是 Legacy users 或 Trigger 尚未同步)
        # Fallback: 嘗試從 itineraries table 找 (舊邏輯，作為安全網)
        print("⚠️ users 表找不到資料，嘗試使用 Legacy Fallback...")
        res_legacy = supabase.table("itineraries")\
            .select("creator_name")\
            .eq("created_by", user_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
            
        if res_legacy.data and len(res_legacy.data) > 0:
            nickname = res_legacy.data[0].get("creator_name", "Legacy Traveler")
            print(f"✅ (Fallback) 找到暱稱: {nickname}")
            return {
                "id": user_id,
                "name": nickname,
                "avatar_url": None
            }

        # 3. 真的找不到
        print("⚠️ 找不到任何記錄，回傳預設值")
        return {
            "id": user_id,
            "name": "New Traveler", 
            "avatar_url": None
        }

    except Exception as e:
        print(f"🔥 Get Profile Error: {e}")
        # 不回傳 500，以免卡死前端，回傳預設值即可
        return {
            "id": user_id,
            "name": "Traveler",
            "avatar_url": None
        }


@router.put("/me")
async def update_user_profile(
    request: UpdateProfileRequest,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """
    ✏️ 更新使用者資料
    
    更新 `public.users` 表。
    Database Trigger (`on_profile_updated`) 會自動同步更新所有的 `trip_members`。
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID")
    
    # 🛡️ Defensive Check: UUID 格式預檢
    if not is_valid_uuid(user_id):
        print(f"🚫 無效的 User ID 格式: {user_id} (update attempt)")
        raise HTTPException(status_code=400, detail=f"Invalid User ID format: {user_id}")
        
    print(f"✏️ Updating user {user_id} data: {request}")
    
    try:
        # 🆕 Normalize User ID: Trim whitespace and ensure valid UUID
        user_id_clean = user_id.strip() if user_id else ""
        if not is_valid_uuid(user_id_clean):
            print(f"🚫 無效的 User ID 格式: '{user_id_clean}' (normalized from '{user_id}')")
            raise HTTPException(status_code=400, detail=f"Invalid User ID format: {user_id_clean}")
            
        user_uuid = str(uuid.UUID(user_id_clean))
        print(f"🔍 Normalized UUID: {user_uuid}")
        
        # 🛡️ Direct HTTP approach - Optimized with async httpx
        
        supabase_url = os.getenv("SUPABASE_URL", "").strip()
        supabase_key = os.getenv("SUPABASE_KEY", "").strip()
        
        if not supabase_url or not supabase_key:
            print("❌ Missing Supabase credentials in .env")
            raise HTTPException(status_code=500, detail="Server configuration error: Missing Supabase credentials")

        headers = build_supabase_rest_headers(
            supabase_key,
            {
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
        )
        
        # Step 1: Check if user exists
        select_cols = "id,avatar_url" if request.avatar_url is not None else "id"
        check_url = f"{supabase_url}/rest/v1/users?id=eq.{user_uuid}&select={select_cols}"
        print(f"📡 Checking existence at: {check_url}")
        
        try:
            # Use the global HTTPX_CLIENT for connection pooling
            check_resp = await HTTPX_CLIENT.get(check_url, headers=headers)
        except Exception as conn_err:
            print(f"🔥 Supabase Connection Error: {conn_err}")
            raise HTTPException(status_code=503, detail="無法連線至資料庫服務，請稍後再試")
        
        if not check_resp.is_success:
            print(f"❌ Check existence failed: {check_resp.status_code} - {check_resp.text}")
            
            if check_resp.status_code == 404:
                print("⚠️ [Resilience] users 資料表不存在！執行降級處理")
                return {
                    "status": "success", 
                    "message": "Profile updated (Local Cache Only)",
                    "data": {"id": user_uuid, "name": request.name}
                }
            
            raise HTTPException(status_code=check_resp.status_code, detail=f"Supabase check failed: {check_resp.text}")

        raw_check_rows = orjson.loads(check_resp.content) if check_resp.content else []
        check_rows = raw_check_rows if isinstance(raw_check_rows, list) else []
        user_exists = len(check_rows) > 0
        old_avatar_url = (
            check_rows[0].get("avatar_url")
            if user_exists and isinstance(check_rows[0], dict)
            else None
        )
        print(f"👤 User exists: {user_exists}")
        
        if user_exists:
            # Step 2a: User exists - PATCH to update
            print(f"📝 Updating existing user: {user_uuid}")
            update_data = {}
            if request.name is not None:
                update_data["name"] = request.name
            if request.avatar_url is not None:
                update_data["avatar_url"] = request.avatar_url
            
            update_url = f"{supabase_url}/rest/v1/users?id=eq.{user_uuid}"
            resp = await HTTPX_CLIENT.patch(update_url, headers=headers, content=orjson.dumps(update_data))
        else:
            # Step 2b: User doesn't exist - POST to insert
            print(f"🆕 Creating new user: {user_uuid}")
            insert_data = {
                "id": user_uuid,
                "name": request.name or "Traveler",
                "avatar_url": request.avatar_url
            }
            insert_url = f"{supabase_url}/rest/v1/users"
            resp = await HTTPX_CLIENT.post(insert_url, headers=headers, content=orjson.dumps(insert_data))
        
        if resp.is_success:
            result_data = orjson.loads(resp.content) if resp.content else []
            if (
                user_exists
                and request.avatar_url is not None
                and isinstance(old_avatar_url, str)
                and old_avatar_url.strip()
            ):
                old_asset = extract_cloudinary_asset(old_avatar_url)
                if old_asset is not None:
                    new_asset = extract_cloudinary_asset(request.avatar_url)
                    should_destroy_old = (
                        new_asset is None
                        or new_asset[1:] != old_asset[1:]
                        or (bool(old_asset[0]) and bool(new_asset[0]) and old_asset[0] != new_asset[0])
                    )
                    if should_destroy_old:
                        await destroy_cloudinary_assets([old_avatar_url])
            print(f"✅ User update/insert success")
            row_data = (
                result_data[0]
                if isinstance(result_data, list) and result_data
                else (result_data if isinstance(result_data, dict) else {"id": user_uuid})
            )
            return {"status": "success", "data": row_data}
        else:
            print(f"🔥 HTTP Error during update: {resp.status_code} - {resp.text}")
            if resp.status_code == 404:
                return {"status": "success", "note": "Table missing, update skipped"}
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 Update Profile Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me/preferences")
async def get_my_preferences(
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🧠 獲取使用者的 AI 記憶偏好 (Adaptive Memory)"""
    try:
        # 單純查詢該使用者的所有偏好
        res = supabase.table("user_preferences").select("*").eq("user_id", user_id).execute()
        return res.data
    except Exception as e:
        print(f"🔥 Get Preferences Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/me/preferences/{pref_id}")
async def delete_my_preference(
    pref_id: str,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🗑️ 刪除特定偏好紀錄"""
    try:
        # 1. 🛡️ 權限檢查：確保這條偏好屬於該使用者 (防止組合攻擊)
        check = supabase.table("user_preferences").select("user_id").eq("id", pref_id).execute()
        
        if not check.data:
            raise HTTPException(status_code=404, detail="偏好項目不存在")
            
        if str(check.data[0]['user_id']) != user_id:
            raise HTTPException(status_code=403, detail="您沒有權限刪除此偏好")
            
        # 2. 執行刪除
        supabase.table("user_preferences").delete().eq("id", pref_id).execute()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 Delete Preference Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
