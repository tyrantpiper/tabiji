"""
GDPR Router
-----------
Handles GDPR compliance endpoints for user data deletion.
"""

from typing import Set
from fastapi import APIRouter, Depends, HTTPException

from routers.users import collect_cloudinary_urls, destroy_cloudinary_assets
from utils.deps import get_supabase, get_verified_user

router = APIRouter(prefix="/api", tags=["gdpr"])


@router.delete("/user/{user_id}/data")
async def delete_user_data(
    user_id: str, 
    caller_user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """
    🗑️ 刪除用戶的所有資料 (GDPR 合規)
    
    刪除順序（避免外鍵約束）：
    1. expenses (消費記錄)
    2. itinerary_items (行程細項)
    3. trip_capsule_entries (旅途膠囊；在刪除主行程前收集 photo_url，因 Supabase 無此表觸發器)
    4. trip_members (成員關係)
    5. itineraries (主行程；itineraries/itinerary_items/expenses 的 Cloudinary 資產由 DB Trigger 清理)
    6. user_preferences / notifications / push_subscriptions
    7. users (用戶主檔，並回收 avatar_url)
    """
    if str(caller_user_id or "").strip().lower() != str(user_id or "").strip().lower():
        raise HTTPException(status_code=403, detail="只能刪除自己的資料")

    target_user_id = str(caller_user_id).strip()

    try:
        print(f"🗑️ GDPR 刪除請求: user_id = {target_user_id}")
        deleted_counts = {}
        media_urls: Set[str] = set()

        def _rows(res) -> list:
            data = getattr(res, "data", None)
            return data if isinstance(data, list) else []

        # 1. 先取得該用戶創建的所有行程 ID
        trips_res = supabase.table("itineraries").select("id").eq("created_by", target_user_id).execute()
        trip_ids = [t["id"] for t in _rows(trips_res) if isinstance(t, dict) and t.get("id")]
        print(f"   📋 找到 {len(trip_ids)} 個行程")
        
        # 2. 刪除消費記錄 (by created_by)
        exp_res = supabase.table("expenses").delete().eq("created_by", target_user_id).execute()
        deleted_counts["expenses"] = len(_rows(exp_res))
        print(f"   ✅ 消費記錄: {deleted_counts['expenses']} 筆")
        
        # 3. 刪除行程細項 (by itinerary_id)
        items_deleted = 0
        for trip_id in trip_ids:
            items_res = supabase.table("itinerary_items").delete().eq("itinerary_id", trip_id).execute()
            items_deleted += len(_rows(items_res))
        deleted_counts["items"] = items_deleted
        print(f"   ✅ 行程細項: {items_deleted} 筆")

        # 3.5. 刪除旅途膠囊 (在主行程級聯刪除前擷取所有 photo_url；此表目前無 DB Trigger 清理)
        capsules_deleted = 0
        author_cap_res = supabase.table("trip_capsule_entries").delete().eq("author_id", target_user_id).execute()
        author_cap_rows = _rows(author_cap_res)
        capsules_deleted += len(author_cap_rows)
        media_urls.update(collect_cloudinary_urls(author_cap_rows, fields=("photo_url",)))
        for trip_id in trip_ids:
            trip_cap_res = supabase.table("trip_capsule_entries").delete().eq("trip_id", trip_id).execute()
            trip_cap_rows = _rows(trip_cap_res)
            capsules_deleted += len(trip_cap_rows)
            media_urls.update(collect_cloudinary_urls(trip_cap_rows, fields=("photo_url",)))
        deleted_counts["capsules"] = capsules_deleted
        print(f"   ✅ 旅途膠囊: {capsules_deleted} 筆")
        
        # 4. 刪除成員關係 (by user_id)
        mem_res = supabase.table("trip_members").delete().eq("user_id", target_user_id).execute()
        deleted_counts["members"] = len(_rows(mem_res))
        print(f"   ✅ 成員關係: {deleted_counts['members']} 筆")
        
        # 5. 刪除主行程 (by creator_id)
        trip_res = supabase.table("itineraries").delete().eq("created_by", target_user_id).execute()
        deleted_counts["trips"] = len(_rows(trip_res))
        print(f"   ✅ 主行程: {deleted_counts['trips']} 筆")

        # 6. 刪除個人偏好設定與無 FK 的通知/推播訂閱
        pref_res = supabase.table("user_preferences").delete().eq("user_id", target_user_id).execute()
        deleted_counts["preferences"] = len(_rows(pref_res))

        notif_res = supabase.table("notifications").delete().eq("user_id", target_user_id).execute()
        deleted_counts["notifications"] = len(_rows(notif_res))

        push_res = supabase.table("push_subscriptions").delete().eq("user_id", target_user_id).execute()
        deleted_counts["push_subscriptions"] = len(_rows(push_res))

        # 7. 刪除使用者主檔並收集大頭貼 URL (此表無 DB Trigger)
        user_res = supabase.table("users").delete().eq("id", target_user_id).execute()
        user_rows = _rows(user_res)
        deleted_counts["users"] = len(user_rows)
        media_urls.update(collect_cloudinary_urls(user_rows, fields=("avatar_url",)))

        deleted_counts["cloudinary_assets"] = await destroy_cloudinary_assets(media_urls)
        
        print(f"🎉 GDPR 刪除完成: {deleted_counts}")
        return {
            "status": "success",
            "message": "所有資料已刪除",
            "deleted": deleted_counts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 GDPR Delete Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
