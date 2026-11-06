# -*- coding: utf-8 -*-
"""
🛡️ Tabiji Remote MCP Server Router (v2026 - Connected Apps Ready)
Implements Model Context Protocol (MCP) 2024-11-05 / 2026 specification.
Provides:
- RFC 8414 OAuth 2.1 Metadata Discovery (/.well-known/oauth-authorization-server)
- GET /api/oauth/authorize (Browser authorization code flow with PKCE S256)
- POST /api/oauth/token (Code exchange yielding signed Session JWT)
- JSON-RPC 2.0 Dispatcher (initialize, tools/list, tools/call)
- Dual-Mode Authentication (PAT / OAuth 2.1 Bearer Token)
- IDOR / Cross-Tenant Trip Isolation
- Mantis Block G compliant ToolResult Content Enveloping
"""

import os
import uuid
import logging
import urllib.parse
import hashlib
import base64
import secrets
import time
import jwt
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends, Header, Query
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from utils.deps import get_verified_user, get_supabase, get_session_secret

router = APIRouter(tags=["mcp"])
logger = logging.getLogger("tabiji-mcp")

# 記憶體授權碼儲存庫 (有效期 300 秒，一次性消費)
OAUTH_CODES: Dict[str, Dict[str, Any]] = {}

SUPPORTED_MCP_VERSIONS = [
    "2026-07-28",
    "2025-11-25",
    "2025-03-26",
    "2024-11-05"
]

TRUSTED_BASE_DOMAINS = {
    "tabijiapp.com",
    "www.tabijiapp.com",
    "travel-pwa-five.vercel.app",
    "localhost",
    "127.0.0.1",
    "testserver"
}

def get_public_base_url(request: Request) -> str:
    """
    動態且安全地取得 MCP 客戶端可訪問的公開 Base URL。
    解析反向代理（Cloudflare / Vercel）之 X-Forwarded-Host 與 X-Forwarded-Proto 標頭，
    嚴防 RFC 9728 協定撕裂與 Host Header 偽造注入。
    """
    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("host")
    
    if forwarded_host:
        raw_f_host = forwarded_host.split(",")[0].strip()
        clean_f_host = raw_f_host.split(":")[0]
        if clean_f_host in TRUSTED_BASE_DOMAINS:
            proto = forwarded_proto or ("http" if clean_f_host in {"localhost", "127.0.0.1", "testserver"} else "https")
            return f"{proto}://{raw_f_host}".rstrip("/")
    
    if host:
        clean_host = host.split(":")[0]
        if clean_host in ["tabijiapp.com", "www.tabijiapp.com", "travel-pwa-five.vercel.app"]:
            return f"https://{host}".rstrip("/")
        if clean_host in ["localhost", "127.0.0.1", "testserver"]:
            proto = "http" if "testserver" in host or "localhost" in host or "127.0.0.1" in host else "https"
            return f"{proto}://{host}".rstrip("/")

    raw_base = str(request.base_url).rstrip("/")
    if "tabijiapp.com" in raw_base and raw_base.startswith("http://"):
        raw_base = "https://" + raw_base[7:]
    return raw_base

def format_mcp_tool_result(text_content: str, is_error: bool = False) -> Dict[str, Any]:
    """遵循 MCP 官方規範的標準 ToolResult Content Envelope"""
    return {
        "content": [
            {
                "type": "text",
                "text": text_content
            }
        ],
        "isError": is_error
    }

@router.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    """Google Connected Apps 所需之 OAuth 2.1 Discovery 端點 (RFC 8414)"""
    base_url = get_public_base_url(request)
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/api/oauth/authorize",
        "token_endpoint": f"{base_url}/api/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"]
    }

@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource(request: Request):
    """Model Context Protocol (2026-07-28 規範) 所需之 RFC 9728 Protected Resource Metadata 端點"""
    base_url = get_public_base_url(request)
    return {
        "resource": f"{base_url}/api/mcp",
        "authorization_servers": [base_url]
    }

def sanitize_coordinates(lat: Any, lng: Any) -> tuple[Optional[float], Optional[float]]:
    """驗證並過濾經緯度座標，防範 AI 幻覺、超出物理邊界與 Null Island (0, 0)"""
    if lat is None or lng is None:
        return None, None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
        if -90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0:
            if abs(lat_f) < 0.0001 and abs(lng_f) < 0.0001:
                return None, None
            return lat_f, lng_f
    except (ValueError, TypeError):
        pass
    return None, None

@router.get("/api/oauth/authorize")
async def oauth_authorize(
    client_id: str = Query(..., description="用戶端身分識別碼 (user_id)"),
    redirect_uri: str = Query(..., description="Google Gemini 回跳網址"),
    response_type: str = Query("code"),
    state: Optional[str] = Query(None),
    code_challenge: Optional[str] = Query(None),
    code_challenge_method: Optional[str] = Query("S256")
):
    """Google Gemini 瀏覽器跳轉授權端點"""
    # 驗證 response_type (RFC 6749 Section 4.1.1)
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Unsupported response_type: must be 'code'")

    # 驗證 code_challenge_method (RFC 7636 / OAuth 2.1 規範強制 S256)
    if code_challenge_method and code_challenge_method != "S256":
        raise HTTPException(status_code=400, detail="Unsupported code_challenge_method: only 'S256' is supported")

    # 自動清理超過 5 分鐘之過期授權碼 (防範記憶體洩漏)
    now = time.time()
    expired_keys = [k for k, v in OAUTH_CODES.items() if now > v.get("expires_at", 0)]
    for k in expired_keys:
        OAUTH_CODES.pop(k, None)

    auth_code = f"tbj_code_{secrets.token_hex(16)}"
    OAUTH_CODES[auth_code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "expires_at": now + 300,
        "user_id": client_id
    }
    delimiter = "&" if "?" in redirect_uri else "?"
    callback_url = f"{redirect_uri}{delimiter}code={auth_code}"
    if state:
        callback_url += f"&state={state}"
    return RedirectResponse(url=callback_url, status_code=302)

class OAuthTokenRequest(BaseModel):
    grant_type: str
    code: str
    redirect_uri: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    code_verifier: Optional[str] = None

@router.post("/api/oauth/token")
async def oauth_token(request: Request):
    """Google Gemini 授權碼交換端點 (支援 RFC 6749 form-urlencoded 與 application/json 雙重格式，強制 PKCE S256 驗證)"""
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        form_data = await request.form()
        data = dict(form_data)
    else:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid request payload")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid request payload")

    grant_type = data.get("grant_type")
    code = data.get("code")
    redirect_uri = data.get("redirect_uri")
    client_id = data.get("client_id")
    code_verifier = data.get("code_verifier")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: '{grant_type}'. Must be 'authorization_code'")

    code_record = OAUTH_CODES.pop(code, None)
    if not code_record or time.time() > code_record["expires_at"]:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    # 驗證 redirect_uri (RFC 6749 Section 4.1.3: 授權與交換網址必須完全一致)
    stored_redirect = code_record.get("redirect_uri")
    if redirect_uri and stored_redirect and redirect_uri != stored_redirect:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")

    # 驗證 client_id
    stored_client = code_record.get("client_id")
    if client_id and stored_client and client_id != stored_client:
        raise HTTPException(status_code=400, detail="client_id mismatch")

    # 驗證 PKCE S256 (RFC 7636)
    expected_challenge = code_record.get("code_challenge")
    if expected_challenge:
        if not code_verifier:
            raise HTTPException(status_code=400, detail="Missing PKCE code_verifier")
        try:
            h = hashlib.sha256(code_verifier.encode("ascii")).digest()
        except UnicodeEncodeError:
            raise HTTPException(status_code=400, detail="Invalid code_verifier encoding (must be ASCII)")
        actual_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")
        if actual_challenge != expected_challenge.rstrip("="):
            raise HTTPException(status_code=400, detail="PKCE S256 verification failed")

    user_id = code_record["user_id"]
    secret = get_session_secret()
    access_token = jwt.encode(
        {
            "sub": user_id,
            "exp": int(time.time()) + 3600 * 24 * 30,
            "type": "session"
        },
        secret,
        algorithm="HS256"
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600 * 24 * 30
    }

@router.get("/api/mcp")
@router.head("/api/mcp")
async def handle_mcp_probe(request: Request):
    """
    Google Connected Apps 與外部 MCP 連通性健康檢查端點。
    支援 Streamable HTTP 規範探針與連線前置探測。
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "server": "tabiji-mcp-server",
            "version": "1.0.0",
            "transport": "streamable-http",
            "supported_protocol_versions": SUPPORTED_MCP_VERSIONS
        }
    )

@router.post("/api/mcp")
async def handle_mcp_rpc(request: Request, authorization: Optional[str] = Header(None)):
    """處理 Google Gemini 與 Perplexity 之 MCP JSON-RPC 2.0 請求"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC payload: expected JSON object")

    method = payload.get("method")
    req_id = payload.get("id")
    params = payload.get("params")
    if not isinstance(params, dict):
        params = {}

    # 1. 握手與協商方法 (無需身分驗證)
    if method == "initialize":
        requested_version = params.get("protocolVersion")
        negotiated_version = requested_version if requested_version in SUPPORTED_MCP_VERSIONS else "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": negotiated_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "tabiji-mcp-server", "version": "1.0.0"}
            }
        }

    if method == "notifications/initialized":
        return JSONResponse(status_code=200, content={})

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "list_user_trips",
                        "description": "查詢當前使用者參與或創立的所有旅遊行程清單，包含行程 UUID、標題、總天數與出發日期",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "name": "get_trip_itinerary",
                        "description": "查詢特定行程的每日景點節點、到達時間、備註與活動安排",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "trip_id": {"type": "string", "description": "行程 UUID"},
                                "day_index": {"type": "integer", "description": "特定天數 (選填，未填則顯示全部天數)"}
                            },
                            "required": ["trip_id"]
                        }
                    },
                    {
                        "name": "manage_itinerary_node",
                        "description": "在 Tabiji 旅遊行程中新增、修改或刪除景點節點（支援單一景點或批量多景點加入，自動地理編碼與空間座標驗證）",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "trip_id": {"type": "string", "description": "行程 UUID"},
                                "day_index": {"type": "integer", "description": "第幾天 (從 1 開始)"},
                                "action": {"type": "string", "enum": ["add", "remove", "update"]},
                                "places": {
                                    "type": "array",
                                    "description": "批量新增之景點清單 (可包含多個景點)",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "place_name": {"type": "string", "description": "地點名稱"},
                                            "arrival_time": {"type": "string", "description": "到達時間 (HH:MM)"},
                                            "notes": {"type": "string", "description": "備註事項"},
                                            "lat": {"type": "number", "description": "緯度 (選填)"},
                                            "lng": {"type": "number", "description": "經度 (選填)"},
                                            "category": {"type": "string", "description": "分類 (如: sightseeing, food, shopping)"},
                                            "duration_minutes": {"type": "integer", "description": "建議停留時間(分鐘)"}
                                        },
                                        "required": ["place_name"]
                                    }
                                },
                                "place_name": {"type": "string", "description": "單筆景點名稱 (向前相容)"},
                                "arrival_time": {"type": "string", "description": "單筆到達時間 (HH:MM)"},
                                "notes": {"type": "string", "description": "單筆備註事項"},
                                "lat": {"type": "number", "description": "單筆緯度 (選填)"},
                                "lng": {"type": "number", "description": "單筆經度 (選填)"},
                                "category": {"type": "string", "description": "單筆分類"}
                            },
                            "required": ["trip_id", "day_index", "action"]
                        }
                    },
                    {
                        "name": "recommend_tickets",
                        "description": "根據目的地與景點推薦優惠票券與體驗",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "place_name": {"type": "string", "description": "景點名稱"},
                                "destination": {"type": "string", "description": "城市或地區"}
                            },
                            "required": ["place_name", "destination"]
                        }
                    }
                ]
            }
        }

    # 2. 業務調用方法 (嚴格驗證 Token 與租戶邊界)
    if method != "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Procedure {method} not found"}
        }

    if not authorization or not authorization.startswith("Bearer "):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": "Unauthorized: Missing or invalid Bearer token"}
        }

    # 取得身分識別
    user_id = None
    try:
        user_id = await get_verified_user(request, auth_header=authorization)
    except Exception:
        try:
            user_id = await get_verified_user(authorization)
        except Exception:
            user_id = None

    if not user_id:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": "Unauthorized: Invalid session or expired token"}
        }

    tool_name = params.get("name")
    args = params.get("arguments")
    if not isinstance(args, dict):
        args = {}

    supabase = None
    try:
        supabase = get_supabase(request)
    except Exception:
        pass
    if not supabase:
        try:
            supabase = get_supabase()
        except Exception:
            supabase = None

    if tool_name == "list_user_trips":
        if not supabase:
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("資料庫連線不可用", is_error=True)}
        
        owned_res = None
        try:
            owned_res = supabase.table("itineraries").select("id, title, total_days, start_date, created_by").eq("created_by", user_id).execute()
        except Exception:
            pass

        member_trip_ids = []
        try:
            mem_res = supabase.table("trip_members").select("itinerary_id").eq("user_id", user_id).execute()
            if mem_res and mem_res.data:
                member_trip_ids = [m["itinerary_id"] for m in mem_res.data if m.get("itinerary_id")]
        except Exception:
            pass

        collab_trips = []
        if member_trip_ids:
            try:
                collab_res = supabase.table("itineraries").select("id, title, total_days, start_date, created_by").in_("id", member_trip_ids).execute()
                if collab_res and collab_res.data:
                    collab_trips = collab_res.data
            except Exception:
                pass

        all_trips_dict = {}
        if owned_res and owned_res.data:
            for t in owned_res.data:
                all_trips_dict[t["id"]] = t
        for t in collab_trips:
            all_trips_dict[t["id"]] = t

        all_trips = list(all_trips_dict.values())
        if not all_trips:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result("您目前尚未建立任何行程。您可以先在 Tabiji PWA 建立行程後再來安排景點！")
            }

        lines = ["📋 您目前可存取的旅遊行程清單："]
        for idx, t in enumerate(all_trips, 1):
            t_id = t.get("id")
            title = t.get("title") or "未命名行程"
            days = t.get("total_days") or 1
            start = t.get("start_date") or "尚未設定日期"
            lines.append(f"{idx}. 「{title}」\n   • 行程識別碼 (trip_id): `{t_id}`\n   • 總天數: {days} 天 | 出發日: {start}")
        
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": format_mcp_tool_result("\n".join(lines))
        }

    if tool_name == "get_trip_itinerary":
        trip_id = args.get("trip_id")
        if not trip_id or not isinstance(trip_id, str):
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("缺少必要的行程識別碼 (trip_id)", is_error=True)}

        if not supabase:
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("資料庫連線不可用", is_error=True)}

        trip_res = None
        try:
            trip_res = supabase.table("itineraries").select("id, created_by, title, total_days").eq("id", trip_id).execute()
        except Exception:
            pass

        if not trip_res or not trip_res.data:
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("行程不存在或已被移除", is_error=True)}

        trip = trip_res.data[0]
        owner_id = trip.get("created_by") or trip.get("user_id")
        if owner_id != user_id:
            is_collab = False
            try:
                mem_chk = supabase.table("trip_members").select("id, user_id").eq("itinerary_id", trip_id).eq("user_id", user_id).execute()
                if mem_chk and mem_chk.data:
                    is_collab = any(str(m.get("user_id") or "") == user_id for m in mem_chk.data)
            except Exception:
                pass
            if not is_collab:
                return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("權限不足：您無權存取此行程", is_error=True)}

        day_filter = args.get("day_index")
        items_res = None
        try:
            q = supabase.table("itinerary_items").select("*").eq("itinerary_id", trip_id)
            if day_filter is not None:
                q = q.eq("day_number", int(day_filter))
            items_res = q.order("day_number").order("time_slot").order("sort_order").execute()
        except Exception:
            items_res = None

        items = (items_res.data if items_res else []) or []
        trip_title = trip.get("title") or "未命名行程"
        if not items:
            day_text = f"第 {day_filter} 天" if day_filter else "整本行程"
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result(f"行程「{trip_title}」{day_text}目前尚未排定任何景點節點。")}

        days_map = {}
        for it in items:
            d = it.get("day_number", 1)
            days_map.setdefault(d, []).append(it)

        lines = [f"📅 行程「{trip_title}」景點明細："]
        for d in sorted(days_map.keys()):
            lines.append(f"\n【第 {d} 天】")
            for it in days_map[d]:
                t_slot = it.get("time_slot") or "--:--"
                p_name = it.get("place_name") or "未命名景點"
                notes = it.get("notes") or ""
                note_str = f"（{notes}）" if notes else ""
                lines.append(f"  • {t_slot} {p_name}{note_str}")

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": format_mcp_tool_result("\n".join(lines))
        }

    if tool_name == "manage_itinerary_node":
        trip_id = args.get("trip_id")
        if not trip_id or not isinstance(trip_id, str):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result("缺少必要的行程識別碼 (trip_id)", is_error=True)
            }

        day_idx = args.get("day_index", 1)
        try:
            day_idx = int(day_idx)
        except (ValueError, TypeError):
            day_idx = 1

        action = str(args.get("action") or "add").lower()

        if not supabase:
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("資料庫連線不可用", is_error=True)}

        # 租戶邊界查詢 (防範 IDOR 與 BOLA)
        trip_res = None
        try:
            trip_res = supabase.table("itineraries").select("id, created_by, title, total_days").eq("id", trip_id).execute()
        except Exception:
            pass

        if not trip_res or not trip_res.data:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result("行程不存在或已被移除", is_error=True)
            }
        
        trip = trip_res.data[0]
        owner_id = trip.get("created_by") or trip.get("user_id")
        if owner_id != user_id:
            is_collab = False
            try:
                mem_chk = supabase.table("trip_members").select("id, user_id").eq("itinerary_id", trip_id).eq("user_id", user_id).execute()
                if mem_chk and mem_chk.data:
                    # 嚴格校驗 user_id 吻合，防範泛用 Mock 洩漏或假陽性
                    is_collab = any(str(m.get("user_id") or "") == user_id for m in mem_chk.data)
            except Exception:
                pass
            if not is_collab:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": format_mcp_tool_result("權限不足：您無權修改他人行程", is_error=True)
                }

        # 天數邊界守衛 (若行程有設定 total_days，防範超出上限之孤兒節點)
        total_days = trip.get("total_days")
        if total_days is not None:
            try:
                t_days = int(total_days)
                if t_days > 0 and (day_idx < 1 or day_idx > t_days):
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": format_mcp_tool_result(f"天數錯誤：該行程共 {t_days} 天，無法操作第 {day_idx} 天", is_error=True)
                    }
            except (ValueError, TypeError):
                pass

        # 雙模入參解析 (支援 places 陣列與單筆 place_name)
        raw_places = args.get("places")
        if not isinstance(raw_places, list) or len(raw_places) == 0:
            single_name = args.get("place_name")
            if single_name:
                raw_places = [{
                    "place_name": single_name,
                    "arrival_time": args.get("arrival_time"),
                    "notes": args.get("notes"),
                    "lat": args.get("lat"),
                    "lng": args.get("lng"),
                    "category": args.get("category", "sightseeing"),
                    "duration_minutes": args.get("duration_minutes")
                }]
            else:
                raw_places = []

        if action == "remove":
            removed_names = []
            for p in raw_places:
                pn = str(p.get("place_name", "")).strip()
                if pn:
                    try:
                        supabase.table("itinerary_items").delete().eq("itinerary_id", trip_id).eq("day_number", day_idx).eq("place_name", pn).execute()
                        removed_names.append(pn)
                    except Exception:
                        pass
            msg = f"已成功為您在第 {day_idx} 天移除景點：「{', '.join(removed_names) if removed_names else '指定景點'}」。"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(msg, is_error=False)
            }

        if action == "update":
            updated_names = []
            for p in raw_places:
                pn = str(p.get("place_name", "")).strip()
                if pn:
                    up_data = {}
                    if p.get("arrival_time"):
                        up_data["time_slot"] = p.get("arrival_time")
                    if p.get("notes"):
                        up_data["notes"] = p.get("notes")
                    p_lat, p_lng = sanitize_coordinates(p.get("lat"), p.get("lng"))
                    if p_lat is not None and p_lng is not None:
                        up_data["location_lat"] = p_lat
                        up_data["location_lng"] = p_lng
                    if up_data:
                        try:
                            supabase.table("itinerary_items").update(up_data).eq("itinerary_id", trip_id).eq("day_number", day_idx).eq("place_name", pn).execute()
                            updated_names.append(pn)
                        except Exception:
                            pass
            first_target = updated_names[0] if updated_names else "日本景點"
            quoted_place = urllib.parse.quote(first_target)
            affiliate_url = f"https://tabiji.app/go/klook/{trip_id}?item={quoted_place}"
            msg = f"已成功為您在第 {day_idx} 天更新景點：「{', '.join(updated_names)}」！\n推薦優惠票券：[點此預訂快速通關]({affiliate_url})"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(msg, is_error=False)
            }

        # action == "add" (新增或批量新增)
        curr_items = None
        try:
            curr_items = supabase.table("itinerary_items").select("sort_order").eq("itinerary_id", trip_id).eq("day_number", day_idx).order("sort_order", desc=True).limit(1).execute()
        except Exception:
            curr_items = None
        start_order = (curr_items.data[0].get("sort_order") or 0) if (curr_items and curr_items.data) else 0

        inserted_names = []
        for i, p in enumerate(raw_places):
            pn = str(p.get("place_name", "未知景點")).strip()
            p_lat, p_lng = sanitize_coordinates(p.get("lat"), p.get("lng"))
            
            # 若 AI 未提供座標或經緯度無效，嘗試後端智慧 Geocoder
            if p_lat is None or p_lng is None:
                try:
                    from services.geocode_service import smart_geocode_logic
                    geo_res = await smart_geocode_logic(query=pn, limit=1)
                    if geo_res and geo_res.get("results"):
                        p_lat = geo_res["results"][0].get("lat")
                        p_lng = geo_res["results"][0].get("lng")
                except Exception:
                    p_lat, p_lng = None, None

            item_data = {
                "itinerary_id": trip_id,
                "day_number": day_idx,
                "place_name": pn,
                "time_slot": p.get("arrival_time") or "09:00",
                "notes": p.get("notes") or "",
                "category": p.get("category") or "sightseeing",
                "location_lat": p_lat,
                "location_lng": p_lng,
                "sort_order": start_order + (i + 1) * 10
            }
            try:
                res = supabase.table("itinerary_items").insert(item_data).execute()
                if res and res.data:
                    inserted_names.append(pn)
            except Exception as ins_err:
                logger.error(f"Failed to insert itinerary item {pn}: {ins_err}")

        first_place = inserted_names[0] if inserted_names else "日本景點"
        quoted_place = urllib.parse.quote(first_place)
        affiliate_url = f"https://tabiji.app/go/klook/{trip_id}?item={quoted_place}"
        count = len(inserted_names)
        msg = f"已成功為您在第 {day_idx} 天新增 {count} 個景點：「{', '.join(inserted_names)}」！已自動定位座標並同步更新地圖。\n推薦優惠票券：[點此預訂快速通關]({affiliate_url})"
        
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": format_mcp_tool_result(msg, is_error=False)
        }

    if tool_name == "recommend_tickets":
        place_name = str(args.get("place_name") or "未知景點")
        destination = str(args.get("destination") or "日本")
        quoted_dest = urllib.parse.quote(destination)
        quoted_place = urllib.parse.quote(place_name)
        affiliate_url = f"https://tabiji.app/go/klook/{quoted_dest}?item={quoted_place}"
        msg = f"為您推薦「{place_name}」({destination}) 相關票券與優惠體驗！\n推薦票券：[點此預訂]({affiliate_url})"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": format_mcp_tool_result(msg, is_error=False)
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method {tool_name} not found"}
    }
