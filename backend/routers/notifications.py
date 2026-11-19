"""
Notifications & Web Push Subscription Router (T1)
-------------------------------------------------
Routes notification reads/mutations and Web Push subscription lifecycle through
server-side FastAPI using JWT-verified user_id (`get_verified_user`) and
`service_role` Supabase access, eliminating client anon RLS blockers and
spoofable `x-user-id` PostgREST headers.
"""

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.deps import get_supabase, get_verified_user

router = APIRouter(tags=["notifications"])


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=1, max_length=2048)
    p256dh: str = Field(..., min_length=1, max_length=512)
    auth: str = Field(..., min_length=1, max_length=512)
    user_agent: Optional[str] = Field(default=None, max_length=512)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=1, max_length=2048)


def _validate_uuid(raw_id: str, field_name: str = "notification_id") -> str:
    try:
        return str(UUID(str(raw_id).strip()))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")


def _validate_https_push_endpoint(endpoint: str) -> str:
    cleaned = (endpoint or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Push subscription endpoint must be a valid https:// URL",
        )
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        raise HTTPException(
            status_code=400,
            detail="Push subscription endpoint host is not allowed",
        )
    return cleaned


@router.get("/api/notifications")
async def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase),
):
    items_res = (
        supabase.table("notifications")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    items = getattr(items_res, "data", None) or []

    unread_res = (
        supabase.table("notifications")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("is_read", False)
        .execute()
    )
    unread_count = getattr(unread_res, "count", None)
    if unread_count is None:
        unread_data = getattr(unread_res, "data", None)
        if isinstance(unread_data, list):
            unread_count = len(unread_data)
        else:
            unread_count = sum(1 for item in items if not item.get("is_read", False))

    return {
        "items": items,
        "unread_count": int(unread_count or 0),
    }


@router.patch("/api/notifications/read-all")
async def mark_all_notifications_read(
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase),
):
    res = (
        supabase.table("notifications")
        .update({"is_read": True})
        .eq("user_id", user_id)
        .eq("is_read", False)
        .execute()
    )
    updated = getattr(res, "data", None) or []
    return {
        "status": "ok",
        "updated_count": len(updated) if isinstance(updated, list) else 0,
    }


@router.patch("/api/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase),
):
    valid_id = _validate_uuid(notification_id, "notification_id")
    res = (
        supabase.table("notifications")
        .update({"is_read": True})
        .eq("id", valid_id)
        .eq("user_id", user_id)
        .execute()
    )
    updated = getattr(res, "data", None) or []
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok", "item": updated[0] if isinstance(updated, list) else updated}


@router.delete("/api/notifications")
async def clear_all_notifications(
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase),
):
    res = (
        supabase.table("notifications")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )
    deleted = getattr(res, "data", None) or []
    return {
        "status": "ok",
        "deleted_count": len(deleted) if isinstance(deleted, list) else 0,
    }


@router.delete("/api/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase),
):
    valid_id = _validate_uuid(notification_id, "notification_id")
    res = (
        supabase.table("notifications")
        .delete()
        .eq("id", valid_id)
        .eq("user_id", user_id)
        .execute()
    )
    deleted = getattr(res, "data", None) or []
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok"}


@router.post("/api/push/subscribe")
async def subscribe_push_notifications(
    body: PushSubscribeRequest,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase),
):
    endpoint = _validate_https_push_endpoint(body.endpoint)
    p256dh = body.p256dh.strip()
    auth = body.auth.strip()
    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Missing push encryption keys")

    payload = {
        "user_id": user_id,
        "endpoint": endpoint,
        "p256dh": p256dh,
        "auth": auth,
        "user_agent": (body.user_agent or "").strip()[:512] or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("push_subscriptions").upsert(
        payload,
        on_conflict="user_id,endpoint",
    ).execute()

    return {"status": "subscribed"}


@router.delete("/api/push/subscribe")
async def unsubscribe_push_notifications(
    body: Optional[PushUnsubscribeRequest] = Body(default=None),
    endpoint_query: Optional[str] = Query(default=None, alias="endpoint"),
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase),
):
    raw_endpoint = (body.endpoint if body else None) or endpoint_query
    endpoint = _validate_https_push_endpoint(raw_endpoint or "")
    supabase.table("push_subscriptions").delete().eq("user_id", user_id).eq("endpoint", endpoint).execute()
    return {"status": "unsubscribed"}
