# -*- coding: utf-8 -*-
"""
Antigravity Agent Router (System 2: Deep Travel Researcher)
----------------------------------------------------------
Handles long-running autonomous research tasks, algorithmic constraint
optimization, and live booking/pricing data mesh using Google's
Interactions API with automated Gemini 3.7 Flash fallback defense.
"""

import os
import time
import uuid
import logging
import asyncio
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
try:
    from google.genai._gaos.lib import compat_errors as _compat_errors
    _INTERACTION_API_ERRORS = (genai_errors.APIError, _compat_errors.APIError)
except ImportError:  # pragma: no cover
    _compat_errors = None
    _INTERACTION_API_ERRORS = (genai_errors.APIError,)

ANTIGRAVITY_AGENT_ID = os.getenv("ANTIGRAVITY_AGENT_ID", "antigravity-preview-09-2026")


def _get_api_error_status(err: Exception) -> Optional[int]:
    code = getattr(err, "code", None)
    if code is None:
        code = getattr(err, "status_code", None)
    return code


def _get_api_error_message(err: Exception) -> str:
    return getattr(err, "message", None) or str(err)

from utils.deps import get_gemini_key
from utils.limiter import limiter
from utils.ai_config import DAILY_ROUTING
from services.model_manager import (
    build_effective_routing,
    classify_api_error,
    extract_clean_response_text,
    get_cached_client,
    record_model_error,
    sanitize_config_for_model,
    summarize_response_diagnostics,
    _execute_with_transient_retry,
    _get_call_timeout,
)

logger = logging.getLogger("ryan-travel-api")
router = APIRouter(prefix="/api/agents", tags=["agents"])

_ORIGINAL_GENAI_CLIENT = genai.Client


def _get_agents_genai_client(api_key: str):
    if genai.Client is not _ORIGINAL_GENAI_CLIENT:
        return genai.Client(api_key=api_key)
    return get_cached_client(api_key)


# In-memory store for fallback tasks
_FALLBACK_TASKS: Dict[str, Dict[str, Any]] = {}


def __reset_fallback_tasks_for_testing() -> None:
    _FALLBACK_TASKS.clear()

TP_BASE = "https://api.travelpayouts.com"
TP_TOKEN = os.getenv("TP_API_TOKEN", "").strip()
TP_MARKER = os.getenv("NEXT_PUBLIC_TP_MARKER", os.getenv("TP_MARKER", "602410")).strip()


class AgentResearchRequest(BaseModel):
    prompt: str = Field(..., description="深度研究主題或複雜計算需求")
    destination: Optional[str] = Field(None, description="目的地城市或機場代碼 (如 NRT / TYO)")
    origin: Optional[str] = Field("TPE", description="出發地機場代碼")
    booking_context: Optional[str] = Field(None, description="用戶已確認的訂單/機票/住宿時間")
    environment: str = Field("remote", description="沙盒環境類型 (remote/local)")
    max_total_tokens: Optional[int] = Field(50000, description="Token 預算上限以防止循環死鎖")
    locale: Optional[str] = Field("zh", description="輸出語系 (zh/en)")


async def _fetch_live_pricing_context(origin: str, destination: str, locale: str = "zh") -> str:
    """
    從 Travelpayouts 抓取即時票價數據以注入 Agent 上下文
    """
    if not TP_TOKEN or not destination:
        return ""
    try:
        is_en = bool(locale and str(locale).strip().lower().startswith("en"))
        dest_clean = destination.strip().upper()[:3]
        orig_clean = origin.strip().upper()[:3]
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                f"{TP_BASE}/aviasales/v3/prices_for_dates",
                params={
                    "origin": orig_clean,
                    "destination": dest_clean,
                    "currency": "TWD",
                    "sorting": "price",
                    "limit": 3,
                    "unique": "false",
                },
                headers={"X-Access-Token": TP_TOKEN},
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    if is_en:
                        lines = [f"[Travelpayouts Live Flight Fare Reference ({orig_clean} -> {dest_clean})]:"]
                        for p in data[:3]:
                            price = p.get("price")
                            airline = p.get("airline", "Airline")
                            dep = p.get("departure_at", "")
                            lines.append(f"- {airline} Departure: {dep} Lowest est. price ~ NT${price:,}")
                        lines.append(f"(Affiliate tracking marker: {TP_MARKER})")
                    else:
                        lines = [f"【Travelpayouts 即時票價參考 ({orig_clean} ➔ {dest_clean})】:"]
                        for p in data[:3]:
                            price = p.get("price")
                            airline = p.get("airline", "航空")
                            dep = p.get("departure_at", "")
                            lines.append(f"- {airline} 出發日:{dep} 最低票價約 NT${price:,}")
                        lines.append(f"（分潤標記追蹤碼: {TP_MARKER}）")
                    return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[Agents] Travelpayouts live pricing fetch skipped: {e}")
    return ""


async def _execute_flash_fallback_task(task_id: str, prompt: str, api_key: str, locale: str = "zh"):
    """
    沙盒排隊/不可用時的 Flash 多模型自動熔斷降級處理器
    """
    try:
        is_en = bool(locale and str(locale).strip().lower().startswith("en"))
        sys_inst = (
            "You are a highly rigorous AI Deep Travel Researcher. "
            "Conduct deep algorithmic analysis and factual research for the traveler's complex itinerary, budget optimization, and transit routes. "
            "When mentioning flights or lodging, include estimated prices and reputable booking platforms. "
            "Format clearly in Markdown (with tables and concise breakdowns), and conclude immediately once done."
            if is_en
            else "你是一位極致嚴謹的 AI 深度旅遊研究副官 (Deep Travel Researcher)。"
            "請針對使用者的複雜行程、預算精算、交通動線進行深度演算與真實性研究。"
            "如果提及機票或住宿，請標記即時預估價格與推薦預訂平台。"
            "請以 Markdown 結構化輸出（包含表格與分析），生成完畢後立即結束，嚴禁贅述。"
        )
        client = _get_agents_genai_client(api_key)
        base_config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            system_instruction=sys_inst,
            max_output_tokens=8192,
            thinking_config=types.ThinkingConfig(thinking_level="low", include_thoughts=False),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        preferred_routing = ["gemini-3.8-flash"] + [m for m in DAILY_ROUTING if m != "gemini-3.8-flash"]
        effective_routing = build_effective_routing("SEARCH", preferred_routing, api_key=api_key)
        last_error: Optional[Exception] = None

        for candidate_model in effective_routing:
            safe_config = None
            timeout_sec = _get_call_timeout("DIAGNOSIS", model_name=candidate_model)
            try:
                safe_config = sanitize_config_for_model(
                    base_config,
                    candidate_model,
                    intent_type="SEARCH",
                    explicit_grounding=True,
                )
                response = await _execute_with_transient_retry(
                    lambda cfg: client.aio.models.generate_content(
                        model=candidate_model,
                        contents=prompt,
                        config=cfg,
                    ),
                    model_name=candidate_model,
                    config=safe_config,
                    timeout_sec=timeout_sec,
                    tag="AgentFallback",
                )
                clean_text = extract_clean_response_text(response)
                if not clean_text or not clean_text.strip():
                    diag = summarize_response_diagnostics(response)
                    logger.warning(f"[Agents] {candidate_model} returned empty visible output: {diag}")
                    record_model_error(candidate_model, api_key=api_key, is_rate_limit=False)
                    last_error = ValueError(f"{candidate_model} empty output ({diag})")
                    continue
                _FALLBACK_TASKS[task_id] = {
                    "status": "completed",
                    "output_text": clean_text,
                    "engine": candidate_model if candidate_model not in ("gemini-3.7-flash", "gemini-3.8-flash") else "gemini-3.7-flash-fallback",
                    "completed_at": time.time(),
                }
                return
            except _INTERACTION_API_ERRORS as e:
                kind = classify_api_error(e)
                if kind == "auth_fail":
                    _FALLBACK_TASKS[task_id] = {
                        "status": "failed",
                        "error": "API Key 無效或已失效，請更新 Gemini API Key。" if not is_en else "Invalid or revoked Gemini API Key.",
                        "code": 401,
                        "engine": "gemini-3.7-flash-fallback",
                    }
                    return
                err_code = _get_api_error_status(e)
                has_search_grounding = any(
                    getattr(t, "google_search", None) is not None
                    for t in (getattr(safe_config, "tools", None) or [])
                )
                # Free Tier GoogleSearch() Grounding 429 不污染全域熔斷器，避免連帶封鎖無須聯網的常規端點
                if kind not in ("bad_request", "config_unsupported") and not (err_code == 429 and has_search_grounding):
                    record_model_error(candidate_model, api_key=api_key, is_rate_limit=(err_code == 429))
                last_error = e
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"[Agents] Candidate {candidate_model} fallback error: {e}")
                continue

        _FALLBACK_TASKS[task_id] = {
            "status": "failed",
            "error": str(last_error or "All fallback models failed"),
            "code": 503,
            "engine": "gemini-3.7-flash-fallback",
        }
    except Exception as e:
        logger.error(f"[Agents] Flash fallback execution error: {e}")
        _FALLBACK_TASKS[task_id] = {
            "status": "failed",
            "error": str(e),
            "code": 500,
            "engine": "gemini-3.7-flash-fallback"
        }


@router.post("/research")
async def start_deep_research(
    body: AgentResearchRequest,
    api_key: str = Depends(get_gemini_key)
):
    """
    啟動 Antigravity 代理人沙盒或 3.7 Flash 降級引擎進行背景深度研究
    """
    is_en = bool(body.locale and str(body.locale).strip().lower().startswith("en"))
    locale_val = body.locale or "zh"

    # 1. 構建包含即時訂單與 Travelpayouts 票價的強化 Prompt
    live_pricing = ""
    if body.destination:
        live_pricing = await _fetch_live_pricing_context(body.origin or "TPE", body.destination, locale=locale_val)

    context_blocks = []
    if body.booking_context:
        ctx_header = "[Confirmed User Booking / Stay Info]" if is_en else "【用戶已確認訂單/住宿資料】"
        context_blocks.append(f"{ctx_header}:\n{body.booking_context}")
    if live_pricing:
        context_blocks.append(live_pricing)

    # 注入 Ralph Loop 防死鎖終止錨點
    if is_en:
        termination_anchor = (
            "\n[System Instruction]: Respond in fluent English. Autonomously compute optimal routes or verify facts in the Linux sandbox. "
            "Finish immediately once the structured Markdown travel report is complete; do not run repeated retry loops."
        )
        req_header = "[Research Task Requirement]"
    else:
        termination_anchor = (
            "\n【系統指令】：請自主在 Linux 沙盒中計算最佳解或爬取真實資料。"
            "生成完結構化 Markdown 旅遊精算報告後立即結束任務，請勿進行重複循環測試。"
        )
        req_header = "【研究任務需求】"

    enhanced_prompt = (
        ("\n\n".join(context_blocks) + "\n\n" if context_blocks else "")
        + f"{req_header}：\n{body.prompt}"
        + termination_anchor
    )

    # 2. 嘗試調用 Antigravity Interactions API
    try:
        client = _get_agents_genai_client(api_key)
        # 🛡️ 遵循 NotebookLM 規範：嚴禁傳遞 temperature 等取樣參數以免 400 錯誤
        interaction = client.interactions.create(
            agent=ANTIGRAVITY_AGENT_ID,
            input=enhanced_prompt,
            environment=body.environment,
            background=True,
            store=True
        )
        return {
            "status": "started",
            "interaction_id": interaction.id,
            "engine": "antigravity",
            "message": "Antigravity Linux sandbox started successfully" if is_en else "Antigravity Linux 沙盒已成功啟動"
        }
    except _INTERACTION_API_ERRORS as e:
        if classify_api_error(e) == "auth_fail":
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired Gemini API Key" if is_en else "Gemini API Key 無效或已過期，請更新金鑰。",
            )
        logger.warning(f"[Agents] Antigravity interactions.create failed ({e}). Falling back to Gemini 3.8 Flash...")
    except Exception as e:
        logger.warning(f"[Agents] Antigravity interactions.create failed ({e}). Falling back to Gemini 3.8 Flash...")

    # 🛡️ 關鍵 0.5 分自動熔斷降級：建立背景 Flash 任務
    task_id = f"fallback_{uuid.uuid4().hex[:12]}"
    _FALLBACK_TASKS[task_id] = {
        "status": "running",
        "output_text": None,
        "engine": "gemini-3.7-flash-fallback",
        "started_at": time.time()
    }
    asyncio.create_task(_execute_flash_fallback_task(task_id, enhanced_prompt, api_key, locale=locale_val))
    return {
        "status": "started",
        "interaction_id": task_id,
        "engine": "gemini-3.7-flash-fallback",
        "message": (
            "Antigravity sandbox is queued; automatically switched to Gemini 3.8 Flash deep reasoning engine"
            if is_en
            else "Antigravity 沙盒排隊中，已自動無縫切換至 Gemini 3.8 Flash 深度推論引擎"
        )
    }


@router.get("/interactions/{interaction_id}")
async def get_interaction_status(
    interaction_id: str,
    api_key: str = Depends(get_gemini_key)
):
    """
    獲取或輪詢 Antigravity 代理人任務進度與研究成果
    """
    # 檢查是否為降級任務
    if interaction_id.startswith("fallback_"):
        task = _FALLBACK_TASKS.get(interaction_id)
        if not task:
            raise HTTPException(status_code=404, detail="Fallback 任務不存在")
        return {
            "id": interaction_id,
            "status": task.get("status", "unknown"),
            "output_text": task.get("output_text"),
            "error": task.get("error"),
            "code": task.get("code"),
            "engine": task.get("engine", "gemini-3.7-flash-fallback")
        }

    # 正常 Antigravity 查詢
    try:
        client = _get_agents_genai_client(api_key)
        interaction = client.interactions.get(id=interaction_id)
        raw_status = str(getattr(interaction, "status", getattr(interaction, "state", "completed"))).lower()
        if "progress" in raw_status or "running" in raw_status:
            normalized_status = "running"
        elif "fail" in raw_status:
            normalized_status = "failed"
        elif "cancel" in raw_status:
            normalized_status = "cancelled"
        else:
            normalized_status = "completed"

        out_text = (
            getattr(interaction, "output_text", None) or
            getattr(interaction, "text", None) or
            getattr(interaction, "output", None)
        )
        return {
            "id": interaction.id,
            "status": normalized_status,
            "output_text": out_text,
            "engine": "antigravity"
        }
    except _INTERACTION_API_ERRORS as e:
        status = _get_api_error_status(e)
        kind = classify_api_error(e)
        if kind == "auth_fail":
            raise HTTPException(status_code=401, detail="Gemini API Key 無效或已失效")
        if status == 400:
            raise HTTPException(status_code=400, detail=f"無效的任務請求: {_get_api_error_message(e)}")
        if status == 404:
            raise HTTPException(status_code=404, detail=f"任務不存在: {interaction_id}")
        if status == 429:
            raise HTTPException(status_code=429, detail="請求頻率過高，請稍後再試")
        raise HTTPException(status_code=503, detail=f"獲取任務狀態失敗: {_get_api_error_message(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Agents] Failed to get interaction {interaction_id}: {e}")
        raise HTTPException(status_code=500, detail=f"獲取任務狀態失敗: {str(e)}")


@router.post("/interactions/{interaction_id}/cancel")
async def cancel_interaction(
    interaction_id: str,
    api_key: str = Depends(get_gemini_key)
):
    """
    🛑 主動取消正在執行的 Antigravity 沙盒任務以節省 Token
    """
    if interaction_id.startswith("fallback_"):
        if interaction_id in _FALLBACK_TASKS:
            _FALLBACK_TASKS[interaction_id]["status"] = "cancelled"
            return {"status": "cancelled", "id": interaction_id}
        raise HTTPException(status_code=404, detail="任務不存在")

    try:
        client = _get_agents_genai_client(api_key)
        client.interactions.cancel(id=interaction_id)
        return {"status": "cancelled", "id": interaction_id}
    except _INTERACTION_API_ERRORS as e:
        status = _get_api_error_status(e)
        if classify_api_error(e) == "auth_fail":
            raise HTTPException(status_code=401, detail="Gemini API Key 無效或已失效")
        if status == 400:
            raise HTTPException(status_code=400, detail=f"無效的取消請求: {_get_api_error_message(e)}")
        if status == 404:
            raise HTTPException(status_code=404, detail=f"任務不存在: {interaction_id}")
        if status == 429:
            raise HTTPException(status_code=429, detail="請求頻率過高，請稍後再試")
        raise HTTPException(status_code=503, detail=f"取消任務失敗: {_get_api_error_message(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Agents] Failed to cancel interaction {interaction_id}: {e}")
        raise HTTPException(status_code=500, detail=f"取消任務失敗: {str(e)}")
