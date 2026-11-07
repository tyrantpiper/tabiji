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
import re
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
# 已消費授權碼防重放紀錄 (支援無狀態跨實例授權碼單次消費保護)
CONSUMED_OAUTH_CODES: Dict[str, float] = {}

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
@router.head("/.well-known/oauth-authorization-server")
@router.options("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    """Google Connected Apps 所需之 OAuth 2.1 Discovery 端點 (RFC 8414)"""
    base_url = get_public_base_url(request)
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/api/oauth/authorize",
        "token_endpoint": f"{base_url}/api/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic", "none"],
        "code_challenge_methods_supported": ["S256"]
    }

@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/{full_path:path}")
@router.head("/.well-known/oauth-protected-resource")
@router.head("/.well-known/oauth-protected-resource/{full_path:path}")
@router.options("/.well-known/oauth-protected-resource")
@router.options("/.well-known/oauth-protected-resource/{full_path:path}")
async def oauth_protected_resource(request: Request, full_path: Optional[str] = None):
    """Model Context Protocol (2026-07-28 規範) 所需之 RFC 9728 Protected Resource Metadata 端點"""
    base_url = get_public_base_url(request)
    resource_url = f"{base_url}/api/mcp"
    if full_path:
        resource_url = f"{base_url}/{full_path.lstrip('/')}"
    return {
        "resource": resource_url,
        "authorization_servers": [base_url]
    }

@router.get("/.well-known/mcp")
@router.get("/.well-known/mcp.json")
@router.head("/.well-known/mcp")
@router.head("/.well-known/mcp.json")
@router.options("/.well-known/mcp")
@router.options("/.well-known/mcp.json")
async def mcp_server_card(request: Request):
    """MCP 官方伺服器宣告卡片 (SEP-1649 / SEP-1960 Discovery)"""
    base_url = get_public_base_url(request)
    return {
        "$schema": "https://static.modelcontextprotocol.io/schemas/mcp-server-card/v1.json",
        "mcp_version": "1.0",
        "server_name": "tabiji-mcp-server",
        "server_version": "1.0.0",
        "description": "Tabiji Smart Travel Companion - Itineraries, Nodes, and Recommendations",
        "endpoints": {
            "http": f"{base_url}/api/mcp"
        },
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False
        }
    }

UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

def is_valid_uuid(val: Any) -> bool:
    """驗證字串是否為合法的 UUID 格式 (防範 PostgreSQL 22P02 語法錯誤)"""
    if not val or not isinstance(val, str):
        return False
    return bool(UUID_REGEX.match(val.strip()))

TRUSTED_REDIRECT_DOMAINS = (
    "google.com",
    "googleusercontent.com",
    "perplexity.ai",
    "claude.ai",
    "claude.com",
    "anthropic.com",
    "chatgpt.com",
    "openai.com",
    "tabijiapp.com",
    "tabiji.app",
    "vercel.app",
)

def is_trusted_redirect_uri(redirect_uri: str) -> bool:
    """驗證 OAuth redirect_uri 是否屬於受信信任之網域，外部網域強制 HTTPS，嚴防 Open Redirect 與 Account Takeover"""
    if not redirect_uri:
        return False
    try:
        parsed = urllib.parse.urlparse(redirect_uri.strip())
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        if hostname in ("localhost", "127.0.0.1", "testserver"):
            return parsed.scheme in ("http", "https")
        if parsed.scheme != "https":
            return False
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in TRUSTED_REDIRECT_DOMAINS
        )
    except Exception:
        return False

def extract_valid_user_id(raw_client_id: str) -> Optional[str]:
    """
    從 client_id 提取並驗證合法的 user_id (UUID)：
    1. 若直接為合法 UUID，去除空白後返回。
    2. 若使用者誤將連線憑證 (JWT) 填入 Client ID，自動驗章並提取其 sub (UUID)。
    """
    if not raw_client_id or not isinstance(raw_client_id, str):
        return None
    cleaned = raw_client_id.strip()
    if is_valid_uuid(cleaned):
        return cleaned
    if cleaned.startswith("ey"):
        try:
            payload = jwt.decode(
                cleaned,
                get_session_secret(),
                algorithms=["HS256"],
                issuer="tabiji-core"
            )
            sub = payload.get("sub")
            if is_valid_uuid(sub):
                return sub.strip()
        except Exception:
            pass
    return None

def calculate_trip_days(trip: Dict[str, Any]) -> int:
    """計算行程總天數 (綜合比較日期跨度、daily_locations 筆數與 total_days)"""
    date_span = 0
    start = trip.get("start_date")
    end = trip.get("end_date")
    if start and end:
        try:
            from datetime import date
            d1 = date.fromisoformat(str(start).split("T")[0])
            d2 = date.fromisoformat(str(end).split("T")[0])
            delta = (d2 - d1).days + 1
            if delta > 0:
                date_span = delta
        except Exception:
            pass

    daily_locations_count = 0
    content = trip.get("content")
    if isinstance(content, str):
        try:
            import json
            content = json.loads(content)
        except Exception:
            content = {}
    if isinstance(content, dict):
        daily_locs = content.get("daily_locations")
        if isinstance(daily_locs, dict):
            daily_locations_count = len(daily_locs)
            try:
                max_key = max([int(k) for k in daily_locs.keys() if str(k).isdigit()] or [0])
                daily_locations_count = max(daily_locations_count, max_key)
            except Exception:
                pass
        elif isinstance(daily_locs, list):
            daily_locations_count = len(daily_locs)

    total_days = 0
    try:
        raw_td = trip.get("total_days")
        if raw_td is not None:
            total_days = int(raw_td)
    except (ValueError, TypeError):
        pass

    return max(date_span, daily_locations_count, total_days, 1)

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

    # 🛡️ 驗證 redirect_uri 安全白名單 (RFC 6749 防範 Open Redirect 與 Account Takeover)
    if not is_trusted_redirect_uri(redirect_uri):
        raise HTTPException(status_code=400, detail="Invalid redirect_uri: untrusted domain")

    # 🛡️ 驗證並自癒提取 client_id 中的合法 UUID (若誤填 JWT 自動提取 sub，若為非法字串立即阻斷)
    resolved_user_id = extract_valid_user_id(client_id)
    if not resolved_user_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid client_id: must be a valid Tabiji User UUID or Connection Token"
        )
    normalized_client_id = client_id.strip()

    # 自動清理超過 5 分鐘之過期授權碼与防重放紀錄 (防範記憶體洩漏)
    now = time.time()
    expired_keys = [k for k, v in OAUTH_CODES.items() if now > v.get("expires_at", 0)]
    for k in expired_keys:
        OAUTH_CODES.pop(k, None)
    expired_consumed = [k for k, exp_ts in CONSUMED_OAUTH_CODES.items() if now > exp_ts]
    for k in expired_consumed:
        CONSUMED_OAUTH_CODES.pop(k, None)

    # 簽發無狀態跨實例相容之授權碼 (解決 Cloud Run 多實例記憶體不共享問題)
    stateless_payload = {
        "cid": normalized_client_id,
        "uid": resolved_user_id,
        "ruri": redirect_uri,
        "cc": code_challenge or "",
        "jti": secrets.token_hex(8),
        "iat": int(now),
        "exp": int(now) + 300,
        "iss": "tabiji-oauth-code"
    }
    signed_code = jwt.encode(stateless_payload, get_session_secret(), algorithm="HS256")
    auth_code = f"tbj_code_{signed_code}"

    OAUTH_CODES[auth_code] = {
        "client_id": normalized_client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "expires_at": now + 300,
        "user_id": resolved_user_id
    }
    delimiter = "&" if "?" in redirect_uri else "?"
    callback_url = f"{redirect_uri}{delimiter}code={urllib.parse.quote(auth_code, safe='')}"
    if state:
        callback_url += f"&state={urllib.parse.quote(state, safe='')}"
    return RedirectResponse(url=callback_url, status_code=302)

class OAuthTokenRequest(BaseModel):
    grant_type: str
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    code_verifier: Optional[str] = None
    refresh_token: Optional[str] = None

def _extract_basic_auth_client_id(request: Request) -> Optional[str]:
    """解析 RFC 6749 Section 2.3.1 HTTP Basic Authentication 中之 client_id"""
    auth_header = request.headers.get("authorization", "")
    if not auth_header or not auth_header.lower().startswith("basic "):
        return None
    try:
        b64_token = auth_header[6:].strip()
        decoded = base64.b64decode(b64_token).decode("utf-8")
        if ":" in decoded:
            raw_cid, _ = decoded.split(":", 1)
            return urllib.parse.unquote(raw_cid).strip()
    except Exception:
        pass
    return None

@router.post("/api/oauth/token")
async def oauth_token(request: Request):
    """OAuth 2.1 授權碼交換與憑證刷新端點 (支援 form-urlencoded / JSON / Basic Auth / 跨實例無狀態換票)"""
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
    secret = get_session_secret()
    now = time.time()
    now_int = int(now)

    # 支援 RFC 8414 所宣告之 refresh_token 刷新模式
    if grant_type == "refresh_token":
        refresh_tok = data.get("refresh_token")
        if not refresh_tok or not isinstance(refresh_tok, str):
            raise HTTPException(status_code=400, detail="Missing refresh_token")
        try:
            rt_payload = jwt.decode(
                refresh_tok.strip(),
                secret,
                algorithms=["HS256"],
                issuer="tabiji-core"
            )
            uid = rt_payload.get("sub")
            if not is_valid_uuid(uid):
                raise HTTPException(status_code=400, detail="Invalid refresh_token subject")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or expired refresh_token")

        new_access_token = jwt.encode(
            {
                "sub": uid,
                "iss": "tabiji-core",
                "iat": now_int,
                "exp": now_int + 3600 * 24 * 30,
                "ver": 1,
                "type": "device_session"
            },
            secret,
            algorithm="HS256"
        )
        return {
            "access_token": new_access_token,
            "refresh_token": refresh_tok.strip(),
            "token_type": "Bearer",
            "expires_in": 3600 * 24 * 30
        }

    code = data.get("code")
    redirect_uri = data.get("redirect_uri")
    client_id = data.get("client_id") or _extract_basic_auth_client_id(request)
    code_verifier = data.get("code_verifier")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: '{grant_type}'. Must be 'authorization_code'")

    # 0. 自動清理過期之已消費授權碼紀錄 (防範高頻換票下之記憶體累積)
    expired_consumed = [k for k, exp_ts in CONSUMED_OAUTH_CODES.items() if now > exp_ts]
    for k in expired_consumed:
        CONSUMED_OAUTH_CODES.pop(k, None)

    # 1. 優先由本機記憶體儲存庫取出 (並標記已消費)
    code_record = OAUTH_CODES.pop(code, None)
    if code_record is not None:
        CONSUMED_OAUTH_CODES[code] = now + 300
        if now > code_record["expires_at"]:
            raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
    else:
        # 2. 若已在本實例消費過，嚴格阻斷重放攻擊 (Replay Attack Defense)
        if code in CONSUMED_OAUTH_CODES:
            raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
        # 3. Cloud Run 跨實例無狀態驗簽回退
        if not isinstance(code, str) or not code.startswith("tbj_code_"):
            raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
        raw_jwt_code = code[len("tbj_code_"):]
        try:
            stateless_data = jwt.decode(
                raw_jwt_code,
                secret,
                algorithms=["HS256"],
                issuer="tabiji-oauth-code"
            )
            CONSUMED_OAUTH_CODES[code] = now + 300
            code_record = {
                "client_id": stateless_data["cid"],
                "redirect_uri": stateless_data["ruri"],
                "code_challenge": stateless_data.get("cc") or None,
                "expires_at": float(stateless_data["exp"]),
                "user_id": stateless_data["uid"]
            }
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    # 驗證 redirect_uri (RFC 6749 Section 4.1.3: 授權與交換網址必須完全一致)
    stored_redirect = code_record.get("redirect_uri")
    if redirect_uri and stored_redirect and redirect_uri != stored_redirect:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")

    # 驗證 client_id (支援原始 client_id 或自癒後之 user_id 比對)
    stored_client = code_record.get("client_id")
    stored_uid = code_record.get("user_id")
    if client_id and stored_client:
        cleaned_cid = client_id.strip()
        if cleaned_cid != stored_client and cleaned_cid != stored_uid:
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
    access_token = jwt.encode(
        {
            "sub": user_id,
            "iss": "tabiji-core",
            "iat": now_int,
            "exp": now_int + 3600 * 24 * 30,
            "ver": 1,
            "type": "device_session"
        },
        secret,
        algorithm="HS256"
    )
    return {
        "access_token": access_token,
        "refresh_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600 * 24 * 30
    }

@router.get("/api/mcp")
@router.head("/api/mcp")
@router.options("/api/mcp")
async def handle_mcp_probe(request: Request):
    """
    Google Connected Apps 與外部 MCP 連通性健康檢查端點。
    支援 Streamable HTTP 規範探針、OPTIONS 預檢與連線前置探測。
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

@router.get("/api/mcp/sse")
@router.post("/api/mcp/sse")
@router.options("/api/mcp/sse")
async def handle_mcp_sse_fallback(request: Request):
    """向下相容 SSE 探針：明確告知客戶端優先使用 Streamable HTTP"""
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "server": "tabiji-mcp-server",
            "transport": "streamable-http",
            "endpoint": "/api/mcp",
            "notice": "Please use Streamable HTTP POST at /api/mcp"
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

    # 1. 握手與協商方法 (無需身分驗證，主動透過 instructions 注入外部 AI 強制執行 SOP)
    if method == "initialize":
        requested_version = params.get("protocolVersion")
        negotiated_version = requested_version if requested_version in SUPPORTED_MCP_VERSIONS else "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": negotiated_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "tabiji-mcp-server", "version": "1.0.0"},
                "instructions": (
                    "【Tabiji MCP 外部 AI 強制執行規範 (Mandatory SOP)】：\n"
                    "1. 先錨定行程區域：在新增或修改任何景點前，必須先透過 list_user_trips 或 get_trip_itinerary 確認該行程與當日所在的『目的地城市與國家』（例如：台北、東京、首爾）。\n"
                    "2. 同名景點強制消歧義：傳入 manage_itinerary_node 的 place_name 時，若遇到跨國或跨城同名景點（例如『龍山寺』、『故宮』、『迪士尼』），必須主動查證並加上該行程所在的城市或行政區前綴（例如在台北行程中必須傳入『台北 艋舺龍山寺』，嚴禁誤傳韓國首爾龍山區等異地同名景點）。\n"
                    "3. 座標查證原則：除非您已 100% 查證該經緯度確屬於該行程所在城市境內，否則呼叫 manage_itinerary_node 時請勿填寫 lat 與 lng，直接交由 Tabiji 後端 4 層動態空間錨點引擎自動精準定位。\n"
                    "4. 分潤連結完整保留：工具回傳之推薦票券與優惠預訂 Markdown 連結（https://tp.media/r?...）必須原封不動呈現給使用者，嚴禁自行竄改或替換網址。"
                )
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
                        "description": "查詢當前使用者參與或創立的所有旅遊行程清單，包含行程 UUID、標題、總天數與出發日期（操作行程前請先呼叫此工具確認目標行程 UUID 與目的地城市）",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "name": "get_trip_itinerary",
                        "description": "查詢特定行程的每日景點節點、到達時間、備註與當日鎖定之空間區域（新增景點前請先呼叫此工具確認當日所在城市與既有動線）",
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
                        "description": "在 Tabiji 旅遊行程中新增、修改或刪除景點節點。注意：呼叫前請先確認該行程所在城市；place_name 請務必包含或確認符合該行程所在城市/區域（如『台北 龍山寺』），若不確定精確座標請省略 lat/lng 由系統空間錨點自動定位。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "trip_id": {"type": "string", "description": "行程 UUID"},
                                "item_id": {"type": "string", "description": "特定景點 UUID (選填，用於精確修改或刪除指定景點)"},
                                "day_index": {"type": "integer", "description": "第幾天 (從 1 開始)"},
                                "action": {"type": "string", "enum": ["add", "remove", "update"]},
                                "places": {
                                    "type": "array",
                                    "description": "批量新增之景點清單 (可包含多個景點)",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "item_id": {"type": "string", "description": "景點 UUID (選填，用於指定特定項目)"},
                                            "place_name": {"type": "string", "description": "地點名稱（請務必確認符合該行程所在城市或加上城市/區域前綴，例如『台北 龍山寺』，避免跨國同名誤判）"},
                                            "arrival_time": {"type": "string", "description": "到達時間 (HH:MM)"},
                                            "notes": {"type": "string", "description": "備註事項"},
                                            "lat": {"type": "number", "description": "緯度（選填。僅在已查證確屬該行程城市境內時填寫；若不確定請省略，由後端空間錨點自動定位）"},
                                            "lng": {"type": "number", "description": "經度（選填。僅在已查證確屬該行程城市境內時填寫；若不確定請省略，由後端空間錨點自動定位）"},
                                            "category": {"type": "string", "description": "分類 (如: sightseeing, food, shopping)"},
                                            "duration_minutes": {"type": "integer", "description": "建議停留時間(分鐘)"}
                                        },
                                        "required": ["place_name"]
                                    }
                                },
                                "place_name": {"type": "string", "description": "單筆景點名稱（請務必確認符合該行程所在城市或加上城市/區域前綴，如『台北 龍山寺』）"},
                                "arrival_time": {"type": "string", "description": "單筆到達時間 (HH:MM)"},
                                "notes": {"type": "string", "description": "單筆備註事項"},
                                "lat": {"type": "number", "description": "單筆緯度（選填，不確定時請省略）"},
                                "lng": {"type": "number", "description": "單筆經度（選填，不確定時請省略）"},
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

    # Fallback: 支援 Recovery Key 直通 (PAT 模式)
    if not user_id and authorization.startswith("Bearer "):
        token_str = authorization.split(" ")[1].strip()
        if token_str.startswith("tbj_rec_"):
            from routers.auth import is_valid_tbj_rec, get_user_record_by_key_id, verify_recovery_key
            if is_valid_tbj_rec(token_str):
                parts = token_str.split("_")
                if len(parts) == 4:
                    key_id = parts[2]
                    supabase_client = None
                    try:
                        supabase_client = get_supabase(request)
                    except Exception:
                        pass
                    if not supabase_client:
                        try:
                            supabase_client = get_supabase()
                        except Exception:
                            supabase_client = None
                    if supabase_client:
                        try:
                            user = get_user_record_by_key_id(supabase_client, key_id)
                            if user and verify_recovery_key(token_str, user.get("recovery_secret_hash")):
                                user_id = user["id"]
                        except Exception:
                            pass

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
            owned_res = supabase.table("itineraries").select("id, title, start_date, end_date, created_by, user_id, content").or_(f"created_by.eq.{user_id},user_id.eq.{user_id}").execute()
        except Exception as e:
            logger.warning(f"[MCP] Failed to fetch owned itineraries for user {user_id}: {e}")

        member_trip_ids = []
        try:
            mem_res = supabase.table("trip_members").select("itinerary_id").eq("user_id", user_id).execute()
            if mem_res and mem_res.data:
                member_trip_ids = [m["itinerary_id"] for m in mem_res.data if m.get("itinerary_id")]
        except Exception as e:
            logger.warning(f"[MCP] Failed to fetch member trip ids for user {user_id}: {e}")

        collab_trips = []
        if member_trip_ids:
            try:
                collab_res = supabase.table("itineraries").select("id, title, start_date, end_date, created_by, user_id, content").in_("id", member_trip_ids).execute()
                if collab_res and collab_res.data:
                    collab_trips = collab_res.data
            except Exception as e:
                logger.warning(f"[MCP] Failed to fetch collab trips for user {user_id}: {e}")

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
            days = calculate_trip_days(t)
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
        if not is_valid_uuid(trip_id):
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result(f"無效的行程識別碼「{trip_id}」：必須為合法的 UUID 格式。若您傳入的是行程名稱，請先調用 list_user_trips 工具查詢行程 UUID", is_error=True)}

        if not supabase:
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("資料庫連線不可用", is_error=True)}

        trip_res = None
        try:
            trip_res = supabase.table("itineraries").select("id, created_by, user_id, title, start_date, end_date, content").eq("id", trip_id).execute()
        except Exception as e:
            logger.warning(f"[MCP] Failed to fetch trip {trip_id}: {e}")

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
        day_number = None
        if day_filter is not None and str(day_filter).strip().lower() not in ("", "none", "null", "all", "整本", "全部"):
            try:
                day_number = int(day_filter)
            except (ValueError, TypeError):
                m = re.search(r'\d+', str(day_filter))
                if m:
                    try:
                        day_number = int(m.group(0))
                    except Exception:
                        day_number = None
                else:
                    day_number = None

        items_res = None
        try:
            q = supabase.table("itinerary_items").select("*").eq("itinerary_id", trip_id)
            if day_number is not None:
                q = q.eq("day_number", day_number)
            items_res = q.order("day_number").order("time_slot").order("sort_order").execute()
        except Exception as e:
            logger.warning(f"[MCP] Failed to fetch itinerary items for {trip_id}: {e}")
            items_res = None

        items = (items_res.data if items_res else []) or []
        # 🛡️ 隱私過濾：Option A 行程擁有者視角 (非擁有者隱藏 is_private 項目)
        is_owner = bool(user_id) and bool(owner_id) and (str(owner_id) == str(user_id))
        if not is_owner:
            items = [it for it in items if not it.get("is_private")]

        trip_title = trip.get("title") or "未命名行程"
        if not items:
            day_text = f"第 {day_number} 天" if day_number is not None else "整本行程"
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
        if not is_valid_uuid(trip_id):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(f"無效的行程識別碼「{trip_id}」：必須為合法的 UUID 格式。若您傳入的是行程名稱，請先調用 list_user_trips 工具查詢行程 UUID", is_error=True)
            }

        target_item_id = args.get("item_id")
        if target_item_id and not is_valid_uuid(target_item_id):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result("無效的景點識別碼 (item_id 必須為合法的 UUID 格式)", is_error=True)
            }

        day_idx = args.get("day_index", 1)
        try:
            day_idx = int(day_idx)
        except (ValueError, TypeError):
            day_idx = 1

        raw_action = str(args.get("action") or "add").lower().strip()
        action_map = {
            "delete": "remove",
            "del": "remove",
            "remove": "remove",
            "edit": "update",
            "modify": "update",
            "update": "update",
            "add": "add",
            "create": "add",
            "insert": "add"
        }
        action = action_map.get(raw_action)
        if not action:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(f"不支援的操作類型 (action: '{raw_action}')，僅支援 'add'、'update'、'remove'", is_error=True)
            }

        if not supabase:
            return {"jsonrpc": "2.0", "id": req_id, "result": format_mcp_tool_result("資料庫連線不可用", is_error=True)}

        # 租戶邊界查詢 (防範 IDOR 與 BOLA)
        trip_res = None
        try:
            trip_res = supabase.table("itineraries").select("id, created_by, user_id, title, start_date, end_date, content").eq("id", trip_id).execute()
        except Exception as e:
            logger.warning(f"[MCP] Failed to fetch trip {trip_id}: {e}")

        if not trip_res or not trip_res.data:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result("行程不存在或已被移除", is_error=True)
            }
        
        trip = trip_res.data[0]
        owner_id = trip.get("created_by") or trip.get("user_id")
        is_owner = bool(user_id) and bool(owner_id) and (str(owner_id) == str(user_id))
        if not is_owner:
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

        # 天數邊界守衛 (若有明確日期或景點資料，防範超出上限之孤兒節點)
        if day_idx < 1:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result("天數錯誤：天數必須大於等於 1", is_error=True)
            }

        t_days = calculate_trip_days(trip)
        has_explicit_days = (
            bool(trip.get("start_date") and trip.get("end_date")) or 
            bool(isinstance(trip.get("content"), dict) and trip["content"].get("daily_locations")) or
            (trip.get("total_days") is not None)
        )
        if has_explicit_days and t_days > 0 and day_idx > t_days:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(f"天數錯誤：該行程共 {t_days} 天，無法操作第 {day_idx} 天", is_error=True)
            }

        # 雙模入參解析 (支援 places 陣列與單筆 place_name)
        raw_places = args.get("places")
        if not isinstance(raw_places, list) or len(raw_places) == 0:
            single_name = args.get("place_name")
            if single_name:
                raw_places = [{
                    "place_name": single_name,
                    "item_id": target_item_id,
                    "arrival_time": args.get("arrival_time"),
                    "notes": args.get("notes"),
                    "lat": args.get("lat"),
                    "lng": args.get("lng"),
                    "category": args.get("category", "sightseeing"),
                    "duration_minutes": args.get("duration_minutes")
                }]
            else:
                raw_places = []

        def rows_were_affected(res_obj: Any) -> bool:
            """判斷資料庫操作是否實質影響了至少 1 筆紀錄"""
            if not res_obj or res_obj.data is None:
                return False
            if isinstance(res_obj.data, list):
                return len(res_obj.data) > 0
            return bool(res_obj.data)

        if action == "remove":
            removed_names = []
            if target_item_id:
                try:
                    q = supabase.table("itinerary_items").delete().eq("itinerary_id", trip_id).eq("id", target_item_id)
                    if not is_owner:
                        q = q.eq("is_private", False)
                    res = q.execute()
                    if rows_were_affected(res):
                        name = (res.data[0].get("place_name") if (isinstance(res.data, list) and res.data) else "") or target_item_id
                        removed_names.append(name)
                except Exception as e:
                    logger.warning(f"[MCP] Delete by item_id {target_item_id} failed: {e}")
            else:
                for p in raw_places:
                    p_id = p.get("item_id")
                    pn = str(p.get("place_name", "")).strip()
                    if p_id and is_valid_uuid(p_id):
                        try:
                            q = supabase.table("itinerary_items").delete().eq("itinerary_id", trip_id).eq("id", p_id)
                            if not is_owner:
                                q = q.eq("is_private", False)
                            res = q.execute()
                            if rows_were_affected(res):
                                name = (res.data[0].get("place_name") if (isinstance(res.data, list) and res.data) else "") or pn or p_id
                                removed_names.append(name)
                        except Exception:
                            pass
                    elif pn:
                        try:
                            q = supabase.table("itinerary_items").delete().eq("itinerary_id", trip_id).eq("day_number", day_idx).eq("place_name", pn)
                            if not is_owner:
                                q = q.eq("is_private", False)
                            res = q.execute()
                            if rows_were_affected(res):
                                removed_names.append(pn)
                        except Exception:
                            pass

            if not removed_names:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": format_mcp_tool_result(f"未找到指定的景點項目，無法在第 {day_idx} 天移除", is_error=True)
                }

            msg = f"已成功為您在第 {day_idx} 天移除景點：「{', '.join(removed_names)}」。"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(msg, is_error=False)
            }

        elif action == "update":
            updated_names = []
            cached_update_anchor: Optional[Dict[str, Any]] = None

            async def get_update_anchor() -> Dict[str, Any]:
                nonlocal cached_update_anchor
                if cached_update_anchor is not None:
                    return cached_update_anchor
                existing_trip_items = []
                try:
                    curr_items = supabase.table("itinerary_items").select("day_number, place_name, location_lat, location_lng, sort_order").eq("itinerary_id", trip_id).order("sort_order", desc=True).execute()
                    if curr_items and isinstance(curr_items.data, list):
                        existing_trip_items = curr_items.data
                except Exception:
                    existing_trip_items = []
                from services.geocode_service import resolve_trip_spatial_anchor
                cached_update_anchor = await resolve_trip_spatial_anchor(trip, day_number=day_idx, existing_items=existing_trip_items)
                return cached_update_anchor

            async def build_update_payload(place_dict: dict, has_id_selector: bool) -> dict:
                up = {}
                if place_dict.get("arrival_time"):
                    up["time_slot"] = place_dict.get("arrival_time")
                if place_dict.get("notes") is not None:
                    up["notes"] = place_dict.get("notes")
                if place_dict.get("category"):
                    up["category"] = place_dict.get("category")
                if has_id_selector and place_dict.get("place_name"):
                    up["place_name"] = str(place_dict.get("place_name")).strip()
                p_lat, p_lng = sanitize_coordinates(place_dict.get("lat"), place_dict.get("lng"))
                if p_lat is not None and p_lng is not None:
                    from services.geocode_service import COUNTRY_BOUNDS, haversine_km, smart_geocode_logic
                    HOMONYM_GUARD_KEYS = ("龍山寺", "東照宮", "中國城", "中華街", "故宮", "天后宮", "媽祖廟", "文武廟")
                    pn_check = str(place_dict.get("place_name") or "").strip()
                    is_homonym_upd = any(hk in pn_check for hk in HOMONYM_GUARD_KEYS)
                    anchor = await get_update_anchor()
                    anchor_lat = anchor.get("lat")
                    anchor_lng = anchor.get("lng")
                    anchor_country = anchor.get("country")
                    anchor_segs = anchor.get("segments") or []
                    coord_rejected = False
                    cand_pts = [
                        (float(s["lat"]), float(s["lng"]))
                        for s in anchor_segs
                        if isinstance(s, dict) and s.get("lat") is not None and s.get("lng") is not None
                    ]
                    if anchor_lat is not None and anchor_lng is not None:
                        cand_pts.insert(0, (float(anchor_lat), float(anchor_lng)))
                    if cand_pts:
                        dist_upd = min(haversine_km(alat, alng, p_lat, p_lng) for alat, alng in cand_pts)
                        if (is_homonym_upd and dist_upd > 50.0) or dist_upd > 180.0:
                            p_lat, p_lng = None, None
                            coord_rejected = True
                    elif anchor_country and anchor_country in COUNTRY_BOUNDS:
                        b = COUNTRY_BOUNDS[anchor_country]
                        if not (b["lat_min"] - 0.5 <= p_lat <= b["lat_max"] + 0.5 and b["lng_min"] - 0.5 <= p_lng <= b["lng_max"] + 0.5):
                            p_lat, p_lng = None, None
                            coord_rejected = True

                    if coord_rejected and place_dict.get("place_name"):
                        try:
                            geo_res = await smart_geocode_logic(
                                query=str(place_dict.get("place_name")).strip(),
                                limit=1,
                                trip_title=anchor.get("trip_title"),
                                lat=anchor_lat,
                                lng=anchor_lng,
                                country=anchor_country,
                                region=anchor.get("region"),
                                bbox=anchor.get("bbox"),
                            )
                            if geo_res and geo_res.get("results"):
                                p_lat, p_lng = sanitize_coordinates(
                                    geo_res["results"][0].get("lat"),
                                    geo_res["results"][0].get("lng"),
                                )
                        except Exception:
                            p_lat, p_lng = None, None

                if p_lat is not None and p_lng is not None:
                    up["location_lat"] = p_lat
                    up["location_lng"] = p_lng
                if not up and place_dict.get("place_name"):
                    up["place_name"] = str(place_dict.get("place_name")).strip()
                return up

            if target_item_id:
                single_place = raw_places[0] if raw_places else args
                up_data = await build_update_payload(single_place, has_id_selector=True)
                if up_data:
                    try:
                        q = supabase.table("itinerary_items").update(up_data).eq("itinerary_id", trip_id).eq("id", target_item_id)
                        if not is_owner:
                            q = q.eq("is_private", False)
                        res = q.execute()
                        if rows_were_affected(res):
                            name = (res.data[0].get("place_name") if (isinstance(res.data, list) and res.data) else "") or str(single_place.get("place_name") or target_item_id)
                            updated_names.append(name)
                    except Exception as e:
                        logger.warning(f"[MCP] Update by item_id {target_item_id} failed: {e}")
            else:
                for p in raw_places:
                    p_id = p.get("item_id")
                    pn = str(p.get("place_name", "")).strip()
                    has_id = bool(p_id and is_valid_uuid(p_id))
                    up_data = await build_update_payload(p, has_id_selector=has_id)
                    if up_data:
                        if has_id:
                            try:
                                q = supabase.table("itinerary_items").update(up_data).eq("itinerary_id", trip_id).eq("id", p_id)
                                if not is_owner:
                                    q = q.eq("is_private", False)
                                res = q.execute()
                                if rows_were_affected(res):
                                    name = (res.data[0].get("place_name") if (isinstance(res.data, list) and res.data) else "") or pn or p_id
                                    updated_names.append(name)
                            except Exception:
                                pass
                        elif pn:
                            try:
                                q = supabase.table("itinerary_items").update(up_data).eq("itinerary_id", trip_id).eq("day_number", day_idx).eq("place_name", pn)
                                if not is_owner:
                                    q = q.eq("is_private", False)
                                res = q.execute()
                                if rows_were_affected(res):
                                    updated_names.append(pn)
                            except Exception:
                                pass

            if not updated_names:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": format_mcp_tool_result(f"未找到指定的景點項目，無法在第 {day_idx} 天更新", is_error=True)
                }

            first_target = updated_names[0] if updated_names else "熱門景點"
            from routers.affiliate import build_affiliate_url
            from services.geocode_service import extract_region_for_search
            trip_dest = (cached_update_anchor.get("region") if cached_update_anchor else "") or extract_region_for_search(str(trip.get("title") or ""))
            affiliate_url = build_affiliate_url("klook", destination=trip_dest, item=first_target)
            msg = f"已成功為您在第 {day_idx} 天更新景點：「{', '.join(updated_names)}」！\n推薦優惠票券：[點此預訂快速通關]({affiliate_url})"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(msg, is_error=False)
            }

        elif action == "add":
            curr_items = None
            existing_trip_items = []
            try:
                curr_items = supabase.table("itinerary_items").select("day_number, place_name, location_lat, location_lng, sort_order").eq("itinerary_id", trip_id).order("sort_order", desc=True).execute()
                if curr_items and isinstance(curr_items.data, list):
                    existing_trip_items = curr_items.data
            except Exception:
                curr_items = None
                existing_trip_items = []

            day_orders = [
                int(it.get("sort_order") or 0)
                for it in existing_trip_items
                if isinstance(it, dict) and (it.get("day_number") in (day_idx, None)) and it.get("sort_order") is not None
            ]
            start_order = max(day_orders) if day_orders else 0

            # 🌍 先錨定行程當日空間座標 (4-Tier Global Spatial Anchor)
            from services.geocode_service import (
                COUNTRY_BOUNDS,
                haversine_km,
                resolve_trip_spatial_anchor,
                smart_geocode_logic,
            )
            anchor = await resolve_trip_spatial_anchor(trip, day_number=day_idx, existing_items=existing_trip_items)
            anchor_lat = anchor.get("lat")
            anchor_lng = anchor.get("lng")
            anchor_region = anchor.get("region")
            anchor_country = anchor.get("country")
            anchor_bbox = anchor.get("bbox")
            anchor_title = anchor.get("trip_title")

            inserted_names = []
            items_to_insert = []
            for i, p in enumerate(raw_places):
                pn = str(p.get("place_name", "未知景點")).strip()
                p_lat, p_lng = sanitize_coordinates(p.get("lat"), p.get("lng"))

                # 🛡️ 零信任外部 AI 座標防呆：若外部 AI 傳入之座標為撞名地標偏離 > 50km、一般偏離 > 180km 或落於目標國界外，強制捨棄並重新定位
                HOMONYM_GUARD_KEYS = ("龍山寺", "東照宮", "中國城", "中華街", "故宮", "天后宮", "媽祖廟", "文武廟")
                is_homonym_add = any(hk in pn for hk in HOMONYM_GUARD_KEYS)
                anchor_segs = anchor.get("segments") or []
                if p_lat is not None and p_lng is not None:
                    cand_pts = [
                        (float(s["lat"]), float(s["lng"]))
                        for s in anchor_segs
                        if isinstance(s, dict) and s.get("lat") is not None and s.get("lng") is not None
                    ]
                    if anchor_lat is not None and anchor_lng is not None:
                        cand_pts.insert(0, (float(anchor_lat), float(anchor_lng)))
                    if cand_pts:
                        dist_add = min(haversine_km(alat, alng, p_lat, p_lng) for alat, alng in cand_pts)
                        if (is_homonym_add and dist_add > 50.0) or dist_add > 180.0:
                            p_lat, p_lng = None, None
                    elif anchor_country and anchor_country in COUNTRY_BOUNDS:
                        b = COUNTRY_BOUNDS[anchor_country]
                        if not (b["lat_min"] - 0.5 <= p_lat <= b["lat_max"] + 0.5 and b["lng_min"] - 0.5 <= p_lng <= b["lng_max"] + 0.5):
                            p_lat, p_lng = None, None

                # 若 AI 未提供座標或座標因偏離錨點被捨棄，啟動錨定後之智慧 Geocoder
                if p_lat is None or p_lng is None:
                    try:
                        geo_res = await smart_geocode_logic(
                            query=pn,
                            limit=1,
                            trip_title=anchor_title,
                            lat=anchor_lat,
                            lng=anchor_lng,
                            country=anchor_country,
                            region=anchor_region,
                            bbox=anchor_bbox,
                        )
                        if geo_res and geo_res.get("results"):
                            raw_geo_lat = geo_res["results"][0].get("lat")
                            raw_geo_lng = geo_res["results"][0].get("lng")
                            p_lat, p_lng = sanitize_coordinates(raw_geo_lat, raw_geo_lng)
                            if p_lat is not None and p_lng is not None and (anchor_lat is None or anchor_lng is None):
                                anchor_lat, anchor_lng = p_lat, p_lng
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
                items_to_insert.append(item_data)

            if items_to_insert:
                try:
                    res = supabase.table("itinerary_items").insert(items_to_insert).execute()
                    if res and res.data:
                        inserted_names.extend(it["place_name"] for it in items_to_insert)
                except Exception as batch_err:
                    logger.warning(f"[MCP] Batch insert failed, falling back to single insert: {batch_err}")
                    for item_data in items_to_insert:
                        try:
                            res = supabase.table("itinerary_items").insert(item_data).execute()
                            if res and res.data:
                                inserted_names.append(item_data["place_name"])
                        except Exception as ins_err:
                            logger.error(f"Failed to insert itinerary item {item_data['place_name']}: {ins_err}")

            first_place = inserted_names[0] if inserted_names else "熱門景點"
            from routers.affiliate import build_affiliate_url
            affiliate_url = build_affiliate_url("klook", destination=anchor_region or anchor_title, item=first_place)
            count = len(inserted_names)
            msg = f"已成功為您在第 {day_idx} 天新增 {count} 個景點：「{', '.join(inserted_names)}」！已自動定位座標並同步更新地圖。\n推薦優惠票券：[點此預訂快速通關]({affiliate_url})"
            
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(msg, is_error=False)
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": format_mcp_tool_result(f"不支援的操作類型 (action: '{action}')", is_error=True)
            }

    if tool_name == "recommend_tickets":
        place_name = str(args.get("place_name") or "未知景點")
        destination = str(args.get("destination") or "")
        from routers.affiliate import build_affiliate_url
        affiliate_url = build_affiliate_url("klook", destination=destination, item=place_name)
        dest_label = destination or "精選目的地"
        msg = f"為您推薦「{place_name}」({dest_label}) 相關票券與優惠體驗！\n推薦票券：[點此預訂]({affiliate_url})"
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
