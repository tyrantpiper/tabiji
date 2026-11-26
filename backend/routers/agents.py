# -*- coding: utf-8 -*-
"""
Antigravity Agent Router (System 2: Deep Travel Researcher)
----------------------------------------------------------
Handles long-running autonomous research tasks, algorithmic constraint
optimization, and live booking/pricing data mesh using Google's
Interactions API with automated Gemini 3.7 Flash fallback defense.
"""

import copy
import hashlib
import hmac
import json
import os
import re
import time
import uuid
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
import httpx
from services.flight_pricing_service import build_flight_price_context

os.environ.setdefault("GOOGLE_GENAI_API_VERSION", "v1beta")

from google import genai
from google.genai import types
from google.genai import errors as genai_errors
_agent_err_types = [genai_errors.APIError]
try:
    from google.genai._gaos.lib import compat_errors as _compat_errors
    _agent_err_types.append(_compat_errors.APIError)
except ImportError:  # pragma: no cover
    _compat_errors = None
try:
    from google.genai._gaos import errors as _gaos_errors
    _agent_err_types.append(_gaos_errors.GenAiError)
except ImportError:  # pragma: no cover
    _gaos_errors = None
_INTERACTION_API_ERRORS = tuple(_agent_err_types)

ANTIGRAVITY_AGENT_ID = os.getenv("ANTIGRAVITY_AGENT_ID", "antigravity-preview-09-2026")


def _get_api_error_status(err: Exception) -> Optional[int]:
    code = getattr(err, "code", None)
    if code is None:
        code = getattr(err, "status_code", None)
    if code is None:
        raw_resp = getattr(err, "raw_response", None)
        code = getattr(raw_resp, "status_code", None)
    return code


def _get_api_error_message(err: Exception) -> str:
    return getattr(err, "message", None) or str(err)

from utils.deps import get_gemini_key, get_supabase
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


# In-memory store for fallback tasks (paired with DB persistence in agent_fallback_tasks)
_FALLBACK_TASKS: Dict[str, Dict[str, Any]] = {}


def __reset_fallback_tasks_for_testing() -> None:
    _FALLBACK_TASKS.clear()


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()


def _resolve_supabase(request: Optional[Request] = None):
    if request is not None:
        overrides = getattr(getattr(request, "app", None), "dependency_overrides", None)
        if isinstance(overrides, dict):
            override = overrides.get(get_supabase)
            if callable(override):
                return override()
        try:
            return get_supabase(request)
        except Exception:
            return None
    try:
        return get_supabase()
    except Exception:
        return None


def _cleanup_expired_fallback_tasks(supabase) -> None:
    if supabase is None:
        return
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        supabase.table("agent_fallback_tasks").delete().lt("expires_at", now_iso).execute()
    except Exception:
        pass


def _persist_fallback_task(
    supabase,
    task_id: str,
    status: str,
    key_hash: str,
    engine: str = "gemini-3.7-flash-fallback",
    output_text: Optional[str] = None,
    error_message: Optional[str] = None,
    code: Optional[int] = None,
) -> None:
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    existing = _FALLBACK_TASKS.get(task_id) or {}
    mem_record: Dict[str, Any] = {
        **existing,
        "id": task_id,
        "status": status,
        "output_text": output_text,
        "error": error_message,
        "code": code,
        "engine": engine,
        "key_hash": key_hash,
        "started_at": existing.get("started_at") or time.time(),
    }
    if status == "completed":
        mem_record["completed_at"] = time.time()
    _FALLBACK_TASKS[task_id] = mem_record

    if supabase is None:
        return
    try:
        db_row = {
            "id": task_id,
            "status": status,
            "output_text": output_text,
            "error_message": error_message,
            "engine": engine,
            "key_hash": key_hash,
            "updated_at": now_iso,
        }
        if status == "running" and "started_at" not in existing:
            db_row["started_at"] = now_iso
            db_row["expires_at"] = (now_dt + timedelta(hours=24)).isoformat()
        supabase.table("agent_fallback_tasks").upsert(db_row, on_conflict="id").execute()
    except Exception as db_err:
        logger.warning(f"[Agents] Persist fallback task skipped ({task_id}): {db_err}")


def _is_fallback_task_cancelled(supabase, task_id: str) -> bool:
    mem = _FALLBACK_TASKS.get(task_id)
    if mem and mem.get("status") == "cancelled":
        return True
    if supabase is not None:
        try:
            res = supabase.table("agent_fallback_tasks").select("status").eq("id", task_id).limit(1).execute()
            rows = getattr(res, "data", None)
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return rows[0].get("status") == "cancelled"
        except Exception:
            pass
    return False


def _load_fallback_task(supabase, task_id: str) -> Optional[Dict[str, Any]]:
    if supabase is not None:
        try:
            res = supabase.table("agent_fallback_tasks").select("*").eq("id", task_id).limit(1).execute()
            rows = getattr(res, "data", None)
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                row = rows[0]
                expires_raw = row.get("expires_at")
                if isinstance(expires_raw, str) and expires_raw.strip():
                    try:
                        exp_dt = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
                        if exp_dt < datetime.now(timezone.utc):
                            return None
                    except Exception:
                        pass
                return row
        except Exception as db_err:
            logger.warning(f"[Agents] Load fallback task DB warning ({task_id}): {db_err}")
    return _FALLBACK_TASKS.get(task_id)

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
    從 Travelpayouts 抓取即時票價數據以注入 Agent 上下文（支援城市名／中文行程標題轉 IATA 與快取）
    """
    if not TP_TOKEN or not destination:
        return ""
    try:
        return await build_flight_price_context(
            origin=origin or "TPE",
            destination=destination,
            locale=locale,
            token=TP_TOKEN,
            marker=TP_MARKER,
            include_marker=True,
            timeout=2.5,
        )
    except Exception as e:
        logger.warning(f"[Agents] Travelpayouts live pricing fetch skipped: {e}")
    return ""


async def _execute_flash_fallback_task(
    task_id: str,
    prompt: str,
    api_key: str,
    locale: str = "zh",
    supabase=None,
    key_hash: str = "",
):
    """
    沙盒排隊/不可用時的 Flash 多模型自動熔斷降級處理器
    """
    key_hash = key_hash or _hash_api_key(api_key)
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
        preferred_routing = ["gemini-4-hydrogen", "gemini-3.8-flash"] + [
            m for m in DAILY_ROUTING if m not in ("gemini-4-hydrogen", "gemini-3.8-flash")
        ]
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
                if await run_in_threadpool(_is_fallback_task_cancelled, supabase, task_id):
                    return
                await run_in_threadpool(
                    _persist_fallback_task,
                    supabase,
                    task_id,
                    status="completed",
                    key_hash=key_hash,
                    engine=candidate_model if candidate_model not in ("gemini-3.7-flash", "gemini-3.8-flash") else "gemini-3.7-flash-fallback",
                    output_text=clean_text,
                )
                return
            except _INTERACTION_API_ERRORS as e:
                kind = classify_api_error(e)
                if kind == "auth_fail":
                    await run_in_threadpool(
                        _persist_fallback_task,
                        supabase,
                        task_id,
                        status="failed",
                        key_hash=key_hash,
                        error_message="API Key 無效或已失效，請更新 Gemini API Key。" if not is_en else "Invalid or revoked Gemini API Key.",
                        code=401,
                    )
                    return
                err_code = _get_api_error_status(e)
                has_search_grounding = any(
                    getattr(t, "google_search", None) is not None
                    for t in (getattr(safe_config, "tools", None) or [])
                )
                # Free Tier GoogleSearch() Grounding 429：立即嘗試剝離 Search Grounding 重試該模型一次（不污染熔斷器）
                if err_code == 429 and has_search_grounding:
                    try:
                        ungrounded_cfg = copy.deepcopy(safe_config)
                        ungrounded_cfg.tools = None
                        ungrounded_resp = await _execute_with_transient_retry(
                            lambda cfg: client.aio.models.generate_content(
                                model=candidate_model,
                                contents=prompt,
                                config=cfg,
                            ),
                            model_name=candidate_model,
                            config=ungrounded_cfg,
                            timeout_sec=timeout_sec,
                            tag="AgentFallbackUngrounded",
                        )
                        ungrounded_text = extract_clean_response_text(ungrounded_resp)
                        if ungrounded_text and ungrounded_text.strip():
                            if await run_in_threadpool(_is_fallback_task_cancelled, supabase, task_id):
                                return
                            await run_in_threadpool(
                                _persist_fallback_task,
                                supabase,
                                task_id,
                                status="completed",
                                key_hash=key_hash,
                                engine=candidate_model if candidate_model not in ("gemini-3.7-flash", "gemini-3.8-flash") else "gemini-3.7-flash-fallback",
                                output_text=ungrounded_text,
                            )
                            return
                    except _INTERACTION_API_ERRORS as e2:
                        kind2 = classify_api_error(e2)
                        if kind2 == "auth_fail":
                            await run_in_threadpool(
                                _persist_fallback_task,
                                supabase,
                                task_id,
                                status="failed",
                                key_hash=key_hash,
                                error_message="API Key 無效或已失效，請更新 Gemini API Key。" if not is_en else "Invalid or revoked Gemini API Key.",
                                code=401,
                            )
                            return
                        err2_code = _get_api_error_status(e2)
                        err2_msg = (_get_api_error_message(e2) or "").lower()
                        if kind2 not in ("bad_request", "config_unsupported") and not (
                            err2_code == 429 and ("grounding" in err2_msg or "search" in err2_msg)
                        ):
                            record_model_error(candidate_model, api_key=api_key, is_rate_limit=(err2_code == 429))
                        last_error = e2
                        continue
                    except Exception as e2:
                        last_error = e2
                        continue
                # Free Tier GoogleSearch() Grounding 429 不污染全域熔斷器，避免連帶封鎖無須聯網的常規端點
                if kind not in ("bad_request", "config_unsupported") and not (err_code == 429 and has_search_grounding):
                    record_model_error(candidate_model, api_key=api_key, is_rate_limit=(err_code == 429))
                last_error = e
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"[Agents] Candidate {candidate_model} fallback error: {e}")
                continue

        await run_in_threadpool(
            _persist_fallback_task,
            supabase,
            task_id,
            status="failed",
            key_hash=key_hash,
            error_message="All fallback models failed. Please try again later.",
            code=503,
        )
    except Exception as e:
        logger.error(f"[Agents] Flash fallback execution error: {e}")
        await run_in_threadpool(
            _persist_fallback_task,
            supabase,
            task_id,
            status="failed",
            key_hash=key_hash,
            error_message="Deep research execution failed. Please try again later.",
            code=500,
        )


@router.post("/research")
async def start_deep_research(
    body: AgentResearchRequest,
    request: Request = None,
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

    # 2. 嘗試調用 Antigravity Interactions API (run_in_threadpool 避免阻塞 Event Loop)
    try:
        client = _get_agents_genai_client(api_key)
        # 🛡️ 遵循 NotebookLM 規範：嚴禁傳遞 temperature 等取樣參數以免 400 錯誤
        interaction = await run_in_threadpool(
            client.interactions.create,
            agent=ANTIGRAVITY_AGENT_ID,
            input=enhanced_prompt,
            environment=body.environment,
            background=True,
            store=True,
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

    # 🛡️ 關鍵 0.5 分自動熔斷降級：建立背景 Flash 任務 (雙寫記憶體 + DB 並綁定 key_hash 雜湊)
    supabase = _resolve_supabase(request)
    await run_in_threadpool(_cleanup_expired_fallback_tasks, supabase)
    task_id = f"fallback_{uuid.uuid4().hex[:12]}"
    key_hash = _hash_api_key(api_key)
    await run_in_threadpool(
        _persist_fallback_task,
        supabase,
        task_id,
        status="running",
        key_hash=key_hash,
        engine="gemini-3.7-flash-fallback",
    )
    asyncio.create_task(
        _execute_flash_fallback_task(
            task_id,
            enhanced_prompt,
            api_key,
            locale=locale_val,
            supabase=supabase,
            key_hash=key_hash,
        )
    )
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


@router.post("/research/stream")
async def stream_deep_research(
    body: AgentResearchRequest,
    request: Request = None,
    api_key: str = Depends(get_gemini_key),
):
    """
    Opt-in Two-Phase SSE 深度研究串流端點：
    - 保持請求活躍（避開 Cloud Run cpu-throttling 背景任務凍結）
    - 每 15 秒送出 `: heartbeat\\n\\n` 保活
    - BYOK Gemini API Key 全程只駐記憶體、零落盤
    """
    is_en = bool(body.locale and str(body.locale).strip().lower().startswith("en"))
    locale_val = body.locale or "zh"

    async def _research_sse_generator():
        yield "event: start\ndata: {}\n\n"
        await asyncio.sleep(0)

        try:
            yield f'event: thinking\ndata: {json.dumps({"status": "researching"})}\n\n'
            await asyncio.sleep(0)

            live_pricing = ""
            if body.destination:
                try:
                    live_pricing = await asyncio.wait_for(
                        _fetch_live_pricing_context(body.origin or "TPE", body.destination, locale=locale_val),
                        timeout=1.5,
                    )
                except Exception:
                    live_pricing = ""

            context_blocks = []
            if body.booking_context:
                ctx_header = "[Confirmed User Booking / Stay Info]" if is_en else "【用戶已確認訂單/住宿資料】"
                context_blocks.append(f"{ctx_header}:\n{body.booking_context}")
            if live_pricing:
                context_blocks.append(live_pricing)

            req_header = "[Research Task Requirement]" if is_en else "【研究任務需求】"
            enhanced_prompt = (
                ("\n\n".join(context_blocks) + "\n\n" if context_blocks else "")
                + f"{req_header}：\n{body.prompt}"
            )

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
            preferred_routing = ["gemini-4-hydrogen", "gemini-3.8-flash"] + [
                m for m in DAILY_ROUTING if m not in ("gemini-4-hydrogen", "gemini-3.8-flash")
            ]
            effective_routing = build_effective_routing("SEARCH", preferred_routing, api_key=api_key)

            final_text = ""
            used_engine = ""

            for candidate_model in effective_routing:
                safe_config = sanitize_config_for_model(
                    base_config,
                    candidate_model,
                    intent_type="SEARCH",
                    explicit_grounding=True,
                )
                timeout_sec = _get_call_timeout("DIAGNOSIS", model_name=candidate_model)

                async def _run_model(cfg):
                    return await _execute_with_transient_retry(
                        lambda c: client.aio.models.generate_content(
                            model=candidate_model,
                            contents=enhanced_prompt,
                            config=c,
                        ),
                        model_name=candidate_model,
                        config=cfg,
                        timeout_sec=timeout_sec,
                        tag="AgentStream",
                    )

                task = asyncio.create_task(_run_model(safe_config))
                try:
                    while not task.done():
                        done_set, _ = await asyncio.wait({task}, timeout=15.0)
                        if not done_set:
                            yield ": heartbeat\n\n"
                            await asyncio.sleep(0)
                    response = task.result()
                    clean_text = extract_clean_response_text(response)
                    if clean_text and clean_text.strip():
                        final_text = clean_text
                        used_engine = candidate_model
                        break
                    record_model_error(candidate_model, api_key=api_key, is_rate_limit=False)
                except _INTERACTION_API_ERRORS as e:
                    kind = classify_api_error(e)
                    if kind == "auth_fail":
                        err_msg = "Invalid or revoked Gemini API Key." if is_en else "API Key 無效或已失效，請更新 Gemini API Key。"
                        yield f'event: error\ndata: {json.dumps({"message": err_msg, "code": 401})}\n\n'
                        return
                    err_code = _get_api_error_status(e)
                    has_grounding = any(
                        getattr(t, "google_search", None) is not None
                        for t in (getattr(safe_config, "tools", None) or [])
                    )
                    if err_code == 429 and has_grounding:
                        try:
                            ungrounded_cfg = copy.deepcopy(safe_config)
                            ungrounded_cfg.tools = None
                            retry_task = asyncio.create_task(_run_model(ungrounded_cfg))
                            while not retry_task.done():
                                done_set, _ = await asyncio.wait({retry_task}, timeout=15.0)
                                if not done_set:
                                    yield ": heartbeat\n\n"
                                    await asyncio.sleep(0)
                            retry_resp = retry_task.result()
                            ungrounded_text = extract_clean_response_text(retry_resp)
                            if ungrounded_text and ungrounded_text.strip():
                                final_text = ungrounded_text
                                used_engine = candidate_model
                                break
                        except Exception:
                            pass
                    if kind not in ("bad_request", "config_unsupported") and not (err_code == 429 and has_grounding):
                        record_model_error(candidate_model, api_key=api_key, is_rate_limit=(err_code == 429))
                    continue
                except asyncio.CancelledError:
                    if not task.done():
                        task.cancel()
                    raise
                except Exception as e:
                    logger.warning(f"[Agents Stream] Candidate {candidate_model} error: {e}")
                    continue

            if final_text:
                yield f'event: text\ndata: {json.dumps({"text": final_text})}\n\n'
                yield f'event: done\ndata: {json.dumps({"model_used": used_engine, "engine": used_engine, "raw_parts": [{"text": final_text}], "sources": []})}\n\n'
            else:
                err_msg = "Deep research models are temporarily unavailable." if is_en else "深度研究引擎暫時忙碌，請稍後再試。"
                yield f'event: error\ndata: {json.dumps({"message": err_msg, "code": 503})}\n\n'
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[Agents Stream] Unexpected error: {e}")
            err_msg = "Deep research stream failed." if is_en else "深度研究串流發生錯誤，請稍後再試。"
            yield f'event: error\ndata: {json.dumps({"message": err_msg, "code": 500})}\n\n'

    return StreamingResponse(
        _research_sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/interactions/{interaction_id}")
async def get_interaction_status(
    interaction_id: str,
    request: Request = None,
    api_key: str = Depends(get_gemini_key)
):
    """
    獲取或輪詢 Antigravity 代理人任務進度與研究成果
    """
    # 檢查是否為降級任務
    if interaction_id.startswith("fallback_"):
        supabase = _resolve_supabase(request)
        task = await run_in_threadpool(_load_fallback_task, supabase, interaction_id)
        if not task:
            raise HTTPException(status_code=404, detail="Fallback 任務不存在")
        stored_hash = task.get("key_hash")
        if stored_hash:
            caller_hash = _hash_api_key(api_key)
            if not hmac.compare_digest(str(stored_hash), caller_hash):
                raise HTTPException(status_code=403, detail="無權存取此深度研究任務")
        return {
            "id": interaction_id,
            "status": task.get("status", "unknown"),
            "output_text": task.get("output_text"),
            "error": task.get("error") or task.get("error_message"),
            "code": task.get("code"),
            "engine": task.get("engine", "gemini-3.7-flash-fallback")
        }

    # 正常 Antigravity 查詢 (run_in_threadpool 避免阻塞 Event Loop)
    try:
        client = _get_agents_genai_client(api_key)
        interaction = await run_in_threadpool(client.interactions.get, id=interaction_id)
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
        if not out_text:
            steps = getattr(interaction, "steps", None)
            if isinstance(steps, list):
                step_texts = []
                for step in steps:
                    if getattr(step, "type", None) == "model_output":
                        content = getattr(step, "content", None)
                        if isinstance(content, list):
                            for item in content:
                                if getattr(item, "type", None) == "text" and isinstance(getattr(item, "text", None), str):
                                    step_texts.append(item.text)
                if step_texts:
                    out_text = "".join(step_texts)
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
        raise HTTPException(status_code=500, detail="獲取任務狀態失敗，請稍後重試")


@router.post("/interactions/{interaction_id}/cancel")
async def cancel_interaction(
    interaction_id: str,
    request: Request = None,
    api_key: str = Depends(get_gemini_key)
):
    """
    🛑 主動取消正在執行的 Antigravity 沙盒任務以節省 Token
    """
    if interaction_id.startswith("fallback_"):
        supabase = _resolve_supabase(request)
        task = await run_in_threadpool(_load_fallback_task, supabase, interaction_id)
        if not task:
            raise HTTPException(status_code=404, detail="任務不存在")
        stored_hash = task.get("key_hash")
        caller_hash = _hash_api_key(api_key)
        if stored_hash and not hmac.compare_digest(str(stored_hash), caller_hash):
            raise HTTPException(status_code=403, detail="無權取消此深度研究任務")
        if interaction_id in _FALLBACK_TASKS:
            _FALLBACK_TASKS[interaction_id]["status"] = "cancelled"
        if supabase is not None:
            def _cancel_db():
                now_iso = datetime.now(timezone.utc).isoformat()
                query = (
                    supabase.table("agent_fallback_tasks")
                    .update({"status": "cancelled", "updated_at": now_iso})
                    .eq("id", interaction_id)
                )
                if stored_hash:
                    query = query.eq("key_hash", caller_hash)
                query.execute()
            try:
                await run_in_threadpool(_cancel_db)
            except Exception as db_err:
                logger.warning(f"[Agents] Cancel DB update skipped ({interaction_id}): {db_err}")
        return {"status": "cancelled", "id": interaction_id}

    try:
        client = _get_agents_genai_client(api_key)
        await run_in_threadpool(client.interactions.cancel, id=interaction_id)
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
        raise HTTPException(status_code=500, detail="取消任務失敗，請稍後重試")
