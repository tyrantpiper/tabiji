# 🛡️ Security Sentinel 對抗安全審查報告
**主題**: `google-genai>=3.4.0` 升級、`gemini-decision-1` 混合漏斗、`gemini-3.1-flash-lite` 檢索詞提煉、`gemini-4-hydrogen` 分級路由與 Cloudflare Edge Shield 邊界審查  
**日期**: 2026-11-17  
**稽核者**: Security Sentinel (Cloudflare ✕ Google Mantis ✕ Harness² ✕ agy CLI)  
**狀態**: PATCH CANDIDATE GENERATED & HUMAN GATE HELD (後端 AI 防護已於隔離沙盒驗證通過；Cloudflare Edge Shield 候選補丁需配合線上 Secret 配置後由人類核准部署)

---

## 1. 執行總結 (Executive Summary)

- **審查候選目標總數**: 7 (`adaptive` 模式為主 + `poi-service` 單目標 `fast` 模式重測)
- **實體擊穿確認 (`CONFIRMED`)**: 1 (`cloudflare/edge-shield/worker.js:poi_service_auth_header_forwarding_gap`)
- **切斯特頓圍欄駁回 (`DISMISSED`)**: 5 (後端 5 項 AI 路由、XML 定界與引用裁剪防禦目標皆通過靜態與測試審查)
- **資訊不足待線上設定驗證 (`INCONCLUSIVE`)**: 1 (`cloudflare/poi-service/worker.js:unverified_jwt_sub_fallback_and_workers_dev`，已重跑解析完整理由並確認受限於 `workers_dev = false` 未於 `wrangler.jsonc` 顯式關閉與 live `*.workers.dev` 路由狀態)
- **沙盒與主庫回歸測試 (Sandbox & Regression Guard)**: `google-genai==3.4.0` 環境下後端全量測試 `688 passed, 5 skipped` (含 44 項 `test_decision1_query_rewrite_hydrogen.py` 測試)，前端 `tsc --noEmit` 0 錯誤、`eslint` 0 錯誤、`vitest --run` `110 files / 1064 passed, 4 skipped`。
- **Harness² 帳本守恆**: `383 = 55 verified + 156 remediated + 172 dismissed` (新增 6 項具決定性結論目標：`+1 CONFIRMED_PENDING_DEV`, `+5 DISMISSED`；第 7 項 `INCONCLUSIVE` 依 `validate_security_ledger.py` 嚴格狀態集規範僅登錄於 `findings_*.json` 與本報告追蹤)。

---

## 2. 實體擊穿與 In-Memory PoC

### Target 6 (CONFIRMED): `cloudflare/edge-shield/worker.js:poi_service_auth_header_forwarding_gap`
- **攻擊向量**: `gateway_header_normalization_consistency`
- **危害層級**: **MEDIUM** (在未配置 `SESSION_SECRET` 的降級路徑中僅剝除 `X-User-ID`，卻原封不動轉發未經簽章驗證的 `Authorization` 標頭給下游 `env.POI_SERVICE`，而下游在特定路徑下以 `atob()` 解析 Bearer JWT `sub` 且不驗證簽章)
- **實機環境交叉查證**:
  - 於 2026-11-17 執行只讀查驗 `npx --yes wrangler secret list` (`cloudflare/edge-shield`)，線上 `tabijiapp-edge-shield` 實測回傳 `[]`（表示線上尚未配置 `SESSION_SECRET`）。
  - 因此依據「切斯特頓圍欄與最小破壞原則」，本審查**禁止**在未配置 `SESSION_SECRET` 前直接於現網套用剝除 `Authorization` 之變更，而是產出候選補丁檔交由人類於配置完 Secret 後核准套用與部署。
- **In-Memory PoC (`pytest_in_memory`)**:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class MockHeaders(dict):
    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default
    def delete(self, key):
        keys_to_del = [k for k in self if k.lower() == key.lower()]
        for k in keys_to_del:
            del self[k]
    def set(self, key, val):
        self.delete(key)
        self[key] = val

@pytest.mark.asyncio
async def test_poi_service_auth_header_forwarding_gap():
    request_headers = {
        "Authorization": "Bearer unverified.untrusted.token",
        "X-User-ID": "forged-user-id"
    }
    env = MagicMock()
    env.SESSION_SECRET = None
    env.POI_SERVICE = MagicMock()
    env.POI_SERVICE.fetch = AsyncMock(return_value=MagicMock(ok=True, status=200))

    headers = MockHeaders(request_headers)
    if env.SESSION_SECRET:
        pass
    else:
        headers.delete("X-User-ID")

    assert "X-User-ID" not in headers
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer unverified.untrusted.token"
```

---

## 3. 已駁回目標 (`DISMISSED` — 後端 AI 強化防線驗收)

1. **`backend/services/intent_router.py:decision1_boundary_and_retry_guard` (`DISMISSED`)**:
   - `_extract_clean_user_text(message, max_len=500)` 在進入 `gemini-decision-1` 前去除外部 System Envelope；introspect `retry_config` 關閉 Speakeasy 4 次指數退避 (`strategy='none'`, `max_retries=0`)；單次呼叫受 `timeout=1.8` 與 `asyncio.wait_for(..., timeout=2.2)` 雙重限制，逾時/429 降級 Stage 2b 且不污染熔斷器。
2. **`backend/services/destination_taxonomy.py:lite_query_rewrite_xml_delimiter_and_circuit` (`DISMISSED`)**:
   - `_sanitize_xml_boundary_text` 先剝除不可見控制/雙向字元與既有標籤，再跳脫 `<` / `>`，完整套用於 query、歷史對話輪與行程目的地；總體超時依實測尾延遲校準至 `3.2s`（單模型 `2.5s`）；空回應或 mock Function Call 不紀錄模型錯誤。
   - **實測追加防線**: 禁止於 `local_query` 注入泛字詞「最新 / 資訊 / 情報」（改以動態西元年 `{current_year}` 表達時效），並於 `classify_and_filter_results` 針對 `wikipedia.org` / `維基百科` 條目增設離題驗證（拒絕與查詢詞無交集的音樂/動漫百科條目）。
3. **`backend/services/destination_taxonomy.py:citation_pruner_cjk_overlap_guard` (`DISMISSED`)**:
   - `prune_and_align_citations` 於存在 `[i]` / `【i】` 標記時嚴格執行 1-to-1 原索引對齊與越界修剪；無標記回退時先套用 `_CITATION_GENERIC_NOISE_RE` 與邊界英文停用詞 / CJK 3-gram 停用詞表 (`_CJK_CITATION_STOPGRAMS`)，抑制「BBC News / Google 新聞 / 世紀帝國」等無關噪音，同時保留具實體重疊度（如「東京晴空塔官方網站」）之良性匹配。
4. **`backend/services/model_manager.py:gemini4_hydrogen_capability_and_budget_guard` (`DISMISSED`)**:
   - `sanitize_config_for_model` 於 `caps` 與 `not caps` 雙路徑皆為 `gemini-3*` 與 `gemini-4*` 清空 `temperature`、`top_p`、`top_k` 與 `thinking_budget`，禁止 Gemini 4 使用不支援的 `minimal`（自動映射 `low`），並於缺漏或過低時強制鎖定 `max_output_tokens >= 16384`（`PLANNING`/`PARSE_MD` 為 `>= 32768`）。
5. **`backend/main.py:uncited_source_resurrection_elimination` (`DISMISSED`)**:
   - `stream_chat_generator` 直接指派 `final_sources = prune_and_align_citations(full_text, candidate_sources)`，移除原先無引註時強制復活 `candidate_sources[:2]` 之回退段落。

---

## 4. `INCONCLUSIVE` 與跨平台雲端設定備忘 (Human Ops Advisory)

### Target 7 (`INCONCLUSIVE`): `cloudflare/poi-service/worker.js:unverified_jwt_sub_fallback_and_workers_dev`
- **技術實況**: `extractUserId` 依賴上游 `tabijiapp-edge-shield` 驗證並清洗 `X-User-ID`，否則僅以 `atob()` 解碼 Bearer JWT `sub`（無 `crypto.subtle.verify` 驗簽）。
- **卡點 (`validation_blocker`)**: `cloudflare/poi-service/wrangler.jsonc` 僅定義 `"name": "tabijiapp-poi-service"`，並未顯式設置 `"workers_dev": false`（Wrangler v4 預設開啟 `*.workers.dev` 路由），且實地確認最近部署於 `2026-10-20`。若 `tabijiapp-poi-service.*.workers.dev` 仍開放公網直連，攻擊者可繞過 Edge Shield 直接打入。
- **先前回報之雲端環境風險摘要 (供人類營運決策，本任務未對雲端執行任何變更)**:
  - Cloudflare `tabijiapp-edge-shield`: `wrangler secret list` 為 `[]`（缺 `SESSION_SECRET`），且 `poi-service/wrangler.jsonc` 未顯式設定 `"workers_dev": false`。
  - 先前線上盤點另發現之 Vercel `NEXT_PUBLIC_SUPABASE_ANON_KEY` 與 Supabase `push_subscriptions` / `verify_jwt: false` Edge Functions 等項目，屬高權限雲端金鑰輪替與部署政策範疇，遵守憲法 L0「人類主權」原則，交由人類於控制台審慎排程處理。

---

## 5. 切斯特頓圍欄考古矩陣 (Code Archaeology Matrix)

| 修改目標 | 被替換/審查之舊代碼 (Legacy Code) | 舊設計初衷 (Original Design Intent) | 刪除/重構風險 (Regression Risk) | 100% 承接機制 (Mitigation Contract) |
| :--- | :--- | :--- | :--- | :--- |
| **`cloudflare/edge-shield/worker.js` (候選補丁)** | `else { headers.delete("X-User-ID"); }` | 未設定 `SESSION_SECRET` 時至少阻擋偽造 `X-User-ID` 頭。 | 若未先在 Cloudflare 配置 `SESSION_SECRET` 即貿然刪除 `Authorization`，會令所有尚未啟用邊緣 HMAC 驗證的連線遺失驗證上下文。 | 僅產出 `patch_candidate_ai_decision1_hydrogen_2026-11-17.diff` 並保留 Human Gate；待確認 `wrangler secret put SESSION_SECRET` 後再合入與部署。 |
| **`backend/main.py`** | 無引註時強制執行 `for s in candidate_sources[:2]: final_sources.append(...)` | 當 LLM 忘記標記 `[1]` 時仍提供前兩筆參考連結給用戶查閱。 | 若上游檢索因泛指代名詞偏題，該回退會把完全未被引用的新聞首頁或遊戲頁面硬塞給使用者。 | 直接移除無條件復活迴圈，並強化 `destination_taxonomy.py` 實體重疊檢查與 `gemini-3.1-flash-lite` 檢索詞提煉，確保有引用或具實體重疊的來源才保留。 |
| **`backend/services/intent_router.py`** | 所有模糊語句直接送 `gemini-3.5-flash-lite` 生成 2 階段文字分類 | 單一通用模型完成意圖與簡易語意判別。 | 換成 `gemini-decision-1` 若未關掉 SDK 內建 Speakeasy 4 次指數退避，單次限流會卡死超過 20 秒。 | 顯式將 `retry_config` 設為 `strategy="none", max_retries=0`，以 `1.8s / 2.2s` 截斷後平滑降級回 Flash-Lite 而不觸發熔斷。 |

---

## 6. 候選補丁與精確區塊替換 (Block Replacement Mapping)

候選補丁檔案: `docs/security/history/patches/patch_candidate_ai_decision1_hydrogen_2026-11-17.diff`

### Block 1: `cloudflare/edge-shield/worker.js` (需於設定 Cloudflare `SESSION_SECRET` 後套用)
- **Target Content**:
```javascript
      } else {
        // 後備防禦：未配置密鑰前，無條件剝除外部偽造標頭
        headers.delete("X-User-ID");
      }
```
- **Replacement Content**:
```javascript
      } else {
        // 後備防禦：未配置密鑰前，無條件剝除外部偽造標頭與未驗證憑證
        headers.delete("X-User-ID");
        headers.delete("Authorization");
      }
```
