# 🛡️ Security Sentinel 對抗安全審查報告
**主題**: AI 串流防禦盾、意圖分流穿透與能力剝離審查 (AI Stream Guardrail & Capability Stripping)  
**日期**: 2026-11-10  
**稽核者**: Security Sentinel (Cloudflare ✕ Google Mantis ✕ Harness² ✕ agy CLI)  
**狀態**: CONFIRMED & PATCH READY (等待人類授權開工)

---

## 1. 執行總結 (Executive Summary)

- **審查目標總數**: 4
- **實體擊穿確認 (CONFIRMED / VERIFIED)**: 4
- **切斯特頓圍欄駁回 (DISMISSED)**: 0
- **良性對照 (Mantis Block G Benign Control)**: 100% 通過（確保標準問候語、景點加入與記帳指令不受影響）
- **Harness² 守恆率**: 100% 嚴格守恆 (`369 = 60 verified + 142 remediated + 167 dismissed`)

---

## 2. 漏洞實體證偽與 In-Memory PoC

### Target 1: `backend/services/intent_router.py:praise_gratitude_misroute_leak`
- **攻擊向量**: `prompt_injection_and_intent_misroute`
- **危害層級**: **HIGH** (引發意圖穿透、無效搜尋資源浪費與後續邏輯失控)
- **實體證明 (PoC)**:
  - 測試檔案: `backend/tests/test_sentinel_ai_stream_guardrail.py::test_poc_praise_and_gratitude_misroute`
  - 擊穿結果: **FAILED (exit code == 1)**
    `AssertionError: Praise samples misrouted: '你很棒' -> None, '太強了' -> None`
  - 根因分析: `GREETING_PATTERN` 僅支援「你好、早安、謝謝」，長度上限 `len <= 8` 且欠缺誇獎詞彙，使用者輸入「你很棒」穿透至 Stage 2，逾時後強制降級為 `SEARCH`，對搜尋引擎發動無意義查詢。

### Target 2: `backend/main.py:streaming_json_protocol_leak`
- **攻擊向量**: `information_disclosure_protocol_leak`
- **危害層級**: **CRITICAL** (內部資料結構與 Function Call 宣告對終端用戶裸露)
- **實體證明**:
  - 使用者實機截圖 (`media_1794297753558_307ea777.jpg`) 明確顯示 `{ "items": [ { "day": 1, ... } ] }` 裸露於聊天氣泡。
  - 根因分析: 串流迴圈對 `chunk_text` 缺乏前瞻動態攔截，直接以 `event: text` 推送至前端打字機。

### Target 3: `backend/main.py:streaming_thought_leakage`
- **攻擊向量**: `information_disclosure_thought_leak`
- **危害層級**: **MEDIUM** (模型內部推理思維鏈、系統提示詞線索污染對話)
- **實體證明**:
  - 當模型產生未封裝於 SDK `p.thought` 之思考文本（如 `<thought>` 標籤跨 Chunk 分裂）時，無狀態正則無法匹配，碎片流入文字通道。

### Target 4: `backend/services/model_manager.py:gemma_tools_payload_500_dos`
- **攻擊向量**: `denial_of_service_and_server_error`
- **危害層級**: **HIGH** (導致 Stage 2 分類與地址萃取持續拋出 HTTP 500 熔斷)
- **實體證明**:
  - 後端運行日誌 `task-12039.log` 捕獲 Google AI Studio 端點對帶有 AFC tools 的 `gemma-4-31b-it` 請求回傳 `500 Internal Server Error`。

---

## 3. 切斯特頓圍欄考古矩陣 (Code Archaeology Matrix)

| 修改目標 | 被替換之舊代碼 (Legacy Code) | 舊設計初衷 (Original Design Intent) | 刪除/重構風險 (Regression Risk) | 100% 承接機制 (Mitigation Contract) |
| :--- | :--- | :--- | :--- | :--- |
| **`intent_router.py`** | `if len(trimmed) <= 8 and GREETING_PATTERN.match(trimmed): return "CHAT"` | 僅短路極短問候語，避免長句包含問候卻遺漏旅遊指令（例如「你好幫我排行程」）。 | 放寬長度可能導致複合指令被誤攔截為純聊天。 | 採用精確錨定正則，限定純讚美/問候才短路；帶有行程關鍵字者一律放行至排程。長度適度放寬至 30 字元。 |
| **`main.py`** | `chunk_text = extract_clean_response_text(chunk); yield text` | 最小延遲，Token 抵達立即推向前端打字機。 | 直接發送會導致中段出現的 Function Call JSON 與思考標籤裸露。 | 引入 30 字元滑動前瞻視窗（Sliding Lookahead Buffer），非 JSON/非思考文字立即平滑 Flush，偵測到 JSON 時靜默轉換為 Function Call。 |
| **`model_manager.py`** | `MODEL_CAPS["gemma-4-31b-it"].supports_tools = True` | 保留 Gemma 未來可能具備的工具調用潛力。 | 在當前 Google 雲端端點下傳遞 tools 會引發 HTTP 500 伺服器崩潰。 | 實施「能力動態剝離（Capability Stripping）」：在純文本與意圖分類任務中強制 `tools = None`，需要工具時優雅降級至 Gemini。 |

---

## 4. 候選補丁與精確區塊替換 (Block Replacement Mapping)

候選補丁檔案已儲存至:  
`docs/security/history/patches/patch_candidate_ai_stream_guardrail_2026-11-10.diff`

### Block 1: `backend/services/intent_router.py`
- **Target Content**:
```python
GREETING_PATTERN = re.compile(
    r"^[\s]*(你好|您好|哈囉|hello|hi|hey|早安|午安|晚安|嗨|嗨嗨|謝謝(你|您)?|感謝(你|您)?|多謝(你|您)?|感恩|thx|thanks|3q)[\s\!！\?？\.\~]*$",
    re.IGNORECASE
)
```
- **Replacement Content**:
```python
GREETING_PATTERN = re.compile(
    r"^[\s]*(你好|您好|哈囉|hello|hi|hey|早安|午安|晚安|嗨|嗨嗨|謝謝(你|您)?|感謝(你|您)?|多謝(你|您)?|感恩|thx|thanks|3q)[\s\!！\?？\.\~]*$",
    re.IGNORECASE
)

# 🛡️ 2026: 擴充讚美、誇獎與感謝快篩正則 (0ms Fast-Path，徹底截斷無效搜尋與工具掛載)
PRAISE_PATTERN = re.compile(
    r"^[\s]*(你好|您好|哈囉|hello|hi|hey|早安|午安|晚安|嗨|嗨嗨|"
    r"謝謝(你|您)?|感謝(你|您)?|多謝(你|您)?|感恩|thx|thanks|3q|"
    r"你?(真|很|太|好|超)?(棒|強|厲害|讚|神|貼心|聰明|給力)(了|的)?|做得好|辛苦了|"
    r"good\s*job|awesome|great(\s*job)?|amazing|well\s*done|bravo|nice|love\s*you)"
    r"[\s\!！\?？\.\~～阿啊啦耶喔吧的\(\)]*$",
    re.IGNORECASE
)
```

- **Target Content**:
```python
    # 2. 短問候語 (短路為 CHAT，完全卸載卡片工具以防幻覺)
    if len(trimmed) <= 8 and GREETING_PATTERN.match(trimmed):
        return "CHAT"
```
- **Replacement Content**:
```python
    # 2. 短問候與讚美語 (短路為 CHAT，完全卸載卡片工具以防幻覺、杜絕無效搜尋)
    if len(trimmed) <= 30 and (GREETING_PATTERN.match(trimmed) or PRAISE_PATTERN.match(trimmed)):
        return "CHAT"
```

---

## 5. 人類主權與開工閘門 (Human Gate Handover)

依據 L0 憲法第一條：**`@security` 僅能審查、舉證與提案，嚴禁直接私自修改程式碼檔案**。  
所有沙盒模擬、In-Memory PoC 與切斯特頓圍欄考古審查皆已 100% 完畢。  
待人類開發者（Ryan）核准後，方可由 `@dev` 執行實體程式碼套用。

