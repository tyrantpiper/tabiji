#!/usr/bin/env python3
"""
scripts/auto_dream.py
=====================
Tabidachi Auto Dream 2.0 (Experience Reflector & Domain Sharded Memory Engine)
Inspired by Google Research Harness2 (Experience Reflector) and Google Mantis.

Features:
1. Deterministic-First Router: Extracts '## 🧬 Machine-Executable Invariant Rules'
   and routes invariants directly to .agents/domains/<domain>.md with 0ms latency & 0 tokens.
2. Deterministic GC: Automatically resolves technical debts marked as RESOLVED.
3. Fallback LLM Recombination: For unformatted daily notes or session logs.
4. Tier 1 Micro-Core Synchronization: Preserves .agents/memory.md within <80 lines budget.
"""

import os
import sys
import re
import time
import json
import asyncio
import argparse
import shutil
from datetime import datetime
from pathlib import Path

def safe_print(*args, **kwargs):
    """Safely print messages, ignoring errors if sys.stdout is detached."""
    if sys.stdout and hasattr(sys.stdout, 'write'):
        try:
            print(*args, **kwargs)
        except Exception:
            pass

# Fix Windows cp950 encoding issues with emojis
if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from scripts.lib.safe_subprocess import run_streaming_process
except ImportError:
    run_streaming_process = None

AGENTS_DIR = os.path.join(PROJECT_ROOT, ".agents")
DOMAINS_DIR = os.path.join(AGENTS_DIR, "domains")
HISTORY_LOG_PATH = os.path.join(AGENTS_DIR, "session_history.log")
MICRO_CORE_MEMORY_PATH = os.path.join(AGENTS_DIR, "memory.md")
IDLE_THRESHOLD_SECONDS = 15 * 60  # 15 minutes

VALID_DOMAINS = {
    "map_webgl",
    "state_cache",
    "ios_ui",
    "offline_pwa",
    "backend_concurrency",
    "devops_security",
}

# Resolve agy CLI path
AGY_CMD = os.environ.get("AGY_BIN", "agy")
if not shutil.which(AGY_CMD):
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    fallback_agy = os.path.join(local_app_data, "agy", "bin", "agy.exe")
    if os.path.exists(fallback_agy):
        AGY_CMD = fallback_agy


def extract_machine_invariants(report_text: str) -> list[dict]:
    """Extract structured Machine-Executable Invariant Rules from report markdown."""
    pattern = r"##\s*🧬\s*Machine-Executable Invariant Rules[\s\S]*?```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(pattern, report_text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError as e:
            safe_print(f"⚠️ [Auto Dream 2.0] Failed to parse JSON invariants: {e}")
    return []


def apply_invariants_deterministically(invariants: list[dict]) -> int:
    """
    Route invariants directly to domain files without calling LLM.
    Returns the number of successfully applied rules.
    """
    if not os.path.exists(DOMAINS_DIR):
        os.makedirs(DOMAINS_DIR, exist_ok=True)

    applied_count = 0

    for item in invariants:
        domain = item.get("domain")
        rule_type = item.get("type", "INVARIANT_RULE")
        rule_id = item.get("id", "")
        title = item.get("title", "")
        content = item.get("content") or item.get("rule", "")
        status = item.get("status", "")

        if domain not in VALID_DOMAINS:
            safe_print(f"⚠️ [Auto Dream 2.0] Unknown domain '{domain}' for rule '{rule_id}', skipping.")
            continue

        domain_file = os.path.join(DOMAINS_DIR, f"{domain}.md")
        if not os.path.exists(domain_file):
            safe_print(f"⚠️ [Auto Dream 2.0] Domain file {domain_file} not found, skipping.")
            continue

        with open(domain_file, "r", encoding="utf-8") as f:
            domain_text = f.read()

        # Handle Technical Debt Resolution (GC)
        if rule_type == "TECHNICAL_DEBT_RESOLUTION" and status == "RESOLVED":
            resolution_note = item.get("resolution", "")
            if rule_id and rule_id in domain_text:
                domain_text = domain_text.replace(
                    rule_id,
                    f"[RESOLVED in {item.get('commit', 'latest')}] {rule_id}"
                )
                with open(domain_file, "w", encoding="utf-8") as f:
                    f.write(domain_text)
                safe_print(f"🧹 [Auto Dream 2.0 GC] Resolved technical debt '{rule_id}' in {domain}.md")
                applied_count += 1
            continue

        # Check if already present to prevent duplicate appending
        rule_signature = f"**{title}**" if title else rule_id
        if rule_signature and rule_signature in domain_text:
            safe_print(f"ℹ️ [Auto Dream 2.0] Invariant '{rule_signature}' already exists in {domain}.md, skipping duplicate.")
            continue

        # Format markdown bullet
        bullet_text = f"- **{title or rule_id}**: {content}\n"

        target_section = "## 🏛️ 架構決策 (Decisions)" if rule_type == "INVARIANT_RULE" else "## 🛡️ 踩坑記錄 (Failed Paths)"

        if target_section in domain_text:
            # Insert right after the section header
            parts = domain_text.split(target_section, 1)
            updated_text = parts[0] + target_section + "\n" + bullet_text + parts[1]
        else:
            # Append section at end
            updated_text = domain_text.rstrip() + f"\n\n{target_section}\n{bullet_text}"

        with open(domain_file, "w", encoding="utf-8") as f:
            f.write(updated_text)

        safe_print(f"🧬 [Auto Dream 2.0] Ingested {rule_type} '{title or rule_id}' -> {domain}.md")
        applied_count += 1

    return applied_count


async def trigger_llm_compaction(history_content: str) -> bool:
    """Fallback LLM Recombination when no structured invariants are present."""
    safe_print(f"[{datetime.now()}] 🧠 [Auto Dream 2.0] 啟動 LLM 備援神經融合...")

    old_memory = ""
    if os.path.exists(MICRO_CORE_MEMORY_PATH):
        with open(MICRO_CORE_MEMORY_PATH, "r", encoding="utf-8") as f:
            old_memory = f.read()

    prompt = f"""
你現在處於 Auto Dream 2.0 狀態。請執行 [Harness Experience Reflection]。
輸入 1 (現有微核心記憶):
{old_memory}

輸入 2 (今日新增日誌):
{history_content}

請將兩者融合，產出精煉的 Markdown 記憶，嚴格維持在 80 行以內，必須包含：
1. ## 🏛️ [Core Invariants] 最高工程鐵律
2. ## 🗺️ [Domain Routing Map] 領域知識庫路由表
3. ## 📖 [Core Vocabulary] 全域核心術語

請只輸出 Markdown 內容，不要包含任何開場白。
    """

    try:
        cmd = [AGY_CMD, "--print", "-"]
        if run_streaming_process:
            res = await run_streaming_process(
                cmd=cmd,
                payload=prompt,
                timeout_seconds=90.0,
                cwd=Path(PROJECT_ROOT),
            )
            stdout = res.stdout
            returncode = res.returncode
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                process.communicate(input=prompt.encode("utf-8")), timeout=90
            )
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
            returncode = process.returncode

        if returncode == 0 and stdout.strip() and ("[Core Invariants]" in stdout or "##" in stdout):
            final_result = stdout.strip()
            with open(MICRO_CORE_MEMORY_PATH, "w", encoding="utf-8") as f:
                f.write(final_result + "\n")
            safe_print(f"[{datetime.now()}] 💾 Auto Dream 2.0 完成！微核心已同步至 {MICRO_CORE_MEMORY_PATH}")
            return True
        return False
    except Exception as e:
        safe_print(f"[{datetime.now()}] ⚠️ Auto Dream 2.0 LLM 調用異常: {e}")
        return False


def process_report_or_history(content: str) -> bool:
    """
    Main processing entrypoint.
    Prioritizes deterministic extraction; falls back to LLM compaction.
    """
    if len(content.strip()) < 50:
        safe_print(f"[{datetime.now()}] ℹ️ 內容不足 50 字元，跳過夢境處理。")
        return False

    invariants = extract_machine_invariants(content)
    if invariants:
        safe_print(f"[{datetime.now()}] ⚡ 偵測到 {len(invariants)} 筆結構化不變量，啟動確定性直通分流...")
        applied = apply_invariants_deterministically(invariants)
        safe_print(f"[{datetime.now()}] 🟢 確定性分流完成！成功處理 {applied} 筆不變量與 GC。")
        return True

    safe_print(f"[{datetime.now()}] ℹ️ 未發現結構化不變量區塊，轉入 LLM 語意備援通道...")
    return asyncio.run(trigger_llm_compaction(content))


def get_last_interaction_time():
    if not os.path.exists(HISTORY_LOG_PATH):
        return None
    return os.path.getmtime(HISTORY_LOG_PATH)


def read_history(path=HISTORY_LOG_PATH):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def daemon_loop():
    safe_print(f"[{datetime.now()}] 🌙 Auto Dream 2.0 守護進程已啟動。監控路徑: {HISTORY_LOG_PATH}")
    while True:
        last_time = get_last_interaction_time()
        if last_time:
            idle_time = time.time() - last_time
            if idle_time >= IDLE_THRESHOLD_SECONDS:
                history_content = read_history()
                if len(history_content.strip()) > 50:
                    success = process_report_or_history(history_content)
                    if success:
                        with open(HISTORY_LOG_PATH, "w", encoding="utf-8") as f:
                            f.write("")
        await asyncio.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tabidachi Auto Dream 2.0")
    parser.add_argument("--trigger", help="手動觸發名稱 (例如 'Daily Wrap-up')")
    parser.add_argument("--inject-report", help="實體報告路徑 (注入神經)")
    parser.add_argument("--daemon", action="store_true", help="強制啟動背景監控")

    args = parser.parse_args()

    try:
        if args.trigger or args.inject_report:
            safe_print(f"[{datetime.now()}] 🚀 接收到神經注入觸發: {args.trigger or 'Report Injection'}")
            content_to_inject = ""
            if args.inject_report:
                if os.path.exists(args.inject_report):
                    with open(args.inject_report, "r", encoding="utf-8") as f:
                        content_to_inject = f.read()
                else:
                    safe_print(f"[{datetime.now()}] ❌ 找不到指定的注入報告: {args.inject_report}")
                    sys.exit(1)
            else:
                content_to_inject = read_history()

            success = process_report_or_history(content_to_inject)
            if success and not args.inject_report:
                with open(HISTORY_LOG_PATH, "w", encoding="utf-8") as f:
                    f.write("")
        else:
            asyncio.run(daemon_loop())
    except KeyboardInterrupt:
        safe_print("\nAuto Dream 2.0 進程已手動停止。")
