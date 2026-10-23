# 📅 Daily Report - 2026-10-24 (Zero-Wire-Leak Architecture, Identity Oracle Defense, Local-First In-Place Reauth & Security Sentinel)

> **系統狀態**：🟢 Production Ready & Security Sentinel Hardened, 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 85 Suites / 565 Tests Passed; Backend 295 Items: 295 Passed, 5 Skipped, 0 Failures; Chrome DevTools MCP 實體遙測閉環通過), Security Ledger 227 Targets (40 Remediated, 51 Verified, 136 Dismissed).
> **今日關鍵研發範疇 (Core Focus)**：
> - 🛡️ **使用者直覺驅動之身分枚舉預言機消解 (Identity Oracle Defense, AD-167)**：由一句「這相當於告訴別人這是別人的啊」引爆出深入骨髓的安全審查。徹底根除錯誤訊息中洩漏金鑰有效性的提示，後端與前端全面統一生產常數錯誤回應 `"引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。"`。
> - 🔐 **網路傳輸層 Token 提前外洩防禦 (Zero-Wire-Leak Architecture, AD-166)**：後端認證契約擴充 `expected_user_id`，在服務端比對身分前**嚴禁生成或序列化任何 JWT**，身分不相符時直接回傳 401，達成傳輸層 100% 零 Token、零 user_id 洩漏，並同步加固舊版 UUID 遷移路徑防止繞過。
> - 📦 **離線寄件匣 401 物理凍結與突變零丟失 (Outbox 401 Freeze & Data Preservation, AD-168)**：徹底修復舊版 `useBackgroundSync` 遭遇 401 時盲目重試 3 次後丟棄未同步行程的致命 Bug。實作 `SyncEngineControl.pause()` 物理急煞機制，保留 retryCount，直到原地重錨定成功後由 `SyncEngineControl.resume()` 依序回放。
> - ⏱️ **5000ms 在途請求冷卻窗口與彈窗抗震盪設計 (Post-Restoration Grace Window, AD-169)**：在 `auth-session.ts` 引入 `lastRestoredAt` 時間戳記，在成功重錨定後 5 秒內，靜默吸收先前在途發出、攜帶舊 Token 的 401 請求，消解彈窗重複震盪 (Modal Thrashing)。
> - 🛑 **登出破壞性清除防護警告 (Destructive Logout Guard, AD-170)**：在個人檔案視圖加入未同步資料提示，若本機存在離線暫存，登出前顯式對話框警告，杜絕 `localStorage.clear()` 誤刪離線行程。
> - 🔬 **Security Sentinel 物理對抗沙盒與 Chrome DevTools MCP 實體遙測**：撰寫 In-Memory PoC（`test_p0_auth_revocation_sentinel_poc.py`）重現漏洞並驗證補丁；在真實應用程式路由（`test_p0_auth_sentinel.py`）執行端點斷言；並透過 Chrome DevTools MCP 於真實瀏覽器中注入事件、實測錯誤提示與離線降級，取得 7 張實體截圖佐證。
> - 📊 **全域安全帳本數學守恆校驗**：修復重複 ID 與長度統計不一致，通過 `python scripts/validate_security_ledger.py` 嚴格校驗（227 標的數學守恆）。

---

## 🏆 深度專案復盤：五項工程與資安里程碑 (Five Core Milestones)

---

### 里程碑一：網路傳輸層 Token 提前外洩防護 (Zero-Wire-Leak Architecture, AD-166)

1. **漏洞根因解剖 (Wire-Level Sequence Flaw)**：
   - 在舊版 `POST /api/auth/session` 中，客戶端請求僅傳入 `{ recovery_key: cleanKey }`。
   - 後端檢索資料庫並驗證雜湊成功後，**立即呼叫 `create_session_jwt` 簽發目標帳號的最新 JWT**，並回傳包含 `access_token` 與 `user_id` 的 JSON Response。
   - 客戶端在收到 Response 後，雖然在 UI 判斷 `if (data.user_id !== currentUuid)` 拋出 Error 並阻止寫入 LocalStorage。
   - **實質危害**：受害者的最高權限 JWT 已經穿過網路到達客戶端記憶體與瀏覽器 DevTools Network Tab，攻擊者可直接透過抓包竊取該 Token 達成帳號劫持。
2. **閉環實作 (Server-Side Expected User ID Gate)**：
   - 後端 `SessionRequest` 擴充 `expected_user_id: Optional[str]`。
   - 後端在取得 `user` 且驗證金鑰成功後，**在呼叫 `create_session_jwt` 之前執行先驗身分斷言**（[`backend/routers/auth.py:208-215`](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py#L208-L215)）：
     ```python
     if body.expected_user_id:
         if user["id"].strip().lower() != body.expected_user_id.strip().lower():
             raise HTTPException(status_code=401, detail=UNIFORM_AUTH_ERROR)
     ```
   - 舊版 UUID 遷移路徑（`is_valid_uuid`）同步加入此斷言（[`Line 223-228`](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py#L223-L228)），杜絕攻擊者傳入 Legacy UUID 繞過防線。
3. **沙盒與端點測試實證**：
   - 經 `backend/tests/test_p0_auth_revocation_sentinel_poc.py::TC-7` 成功物理重現 Wire JWT Leak。
   - 經 `test_p0_auth_sentinel.py::test_auth_session_server_side_expected_user_id_mismatch_blocks_jwt_and_prevents_oracle` 實測證明：身分不符時，Response Body 100% 零 `access_token`、零 `user_id` 傳輸。

---

### 里程碑二：使用者直覺驅動之身分枚舉預言機消解 (Identity Oracle Defense, AD-167)

1. **直覺叩問與預言機破口**：
   - 原先客戶端在身分不相符時拋出：`🚨 身分不相符：此引繼碼屬於另一個帳號！`。
   - 使用者提出核心質疑：*「此引繼碼屬於另一個帳號，不可以顯示啊，不可以告訴別人吶，這相當于說你看這是別人的！」*
   - **預言機危害**：攻擊者輸入探測金鑰時，若收到「屬於另一個帳號」，系統直接充當存在性預言機（Existence Oracle），確認該金鑰在資料庫中真實存在且已綁定活躍用戶，大幅縮小字典探測空間。
2. **統一常數防線**：
   - 後端定義常數：`UNIFORM_AUTH_ERROR = "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。"`。
   - 前端定義常數：`UNIFORM_REAUTH_ERROR = "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。"`。
   - 無論是格式異常、金鑰不存在、雜湊比對失敗、或是 `expected_user_id` 身分不符，全鏈路統一回傳相同錯誤，徹底消解側信道資訊洩漏。
3. **Chrome DevTools MCP 實體遙測佐證**：
   - 在運行中的 `http://localhost:3000/` 注入無效金鑰與外來金鑰，實測截圖證實 UI 紅色錯誤框完全一致，且 `has_oracle_leak: false`。

---

### 里程碑三：離線寄件匣 401 物理凍結與突變零丟失 (Outbox 401 Freeze, AD-168)

1. **離線優先（Local-First）之致命盲點**：
   - 舊版 `frontend/lib/sync-hooks.ts` 中的 `useBackgroundSync` 在連網時依序重放 IndexedDB 的離線請求。
   - 當裝置遭遇 401（憑證輪替或過期）時，程序將 401 當作一般暫態錯誤，執行 `item.retryCount++`。在重試 3 次後，呼叫 `SyncQueue.dequeue(req.id)` 將請求移出佇列。
   - **後果**：使用者在離線期間建立的行程、記帳在背景被永久刪除，造成資料滅失。
2. **物理凍結機制與原地重錨閉環**：
   - 在 `frontend/lib/sync-engine.ts` 引入單例 `SyncEngineControl`（`pause()`, `resume()`, `isPaused()`）。
   - 在 `frontend/lib/sync-hooks.ts` 第 129 行：遭遇 401 時立即執行 `SyncEngineControl.pause(); triggerReauthPrompt(); break;`。
   - **鐵律**：絕對不累加 retryCount，絕對不 dequeue，物理中斷回放迴圈。
   - 使用者在 `SessionReauthModal` 輸入正確引繼碼完成 `reanchorSessionWithKey` 後，呼叫 `SyncEngineControl.resume()`，佇列中的離線請求以新 Token 依序沖刷寫入資料庫。
3. **測試覆蓋**：
   - `frontend/__tests__/in-place-reauth-resilience.test.ts` TC-1（重現漏洞）、TC-2（驗證凍結）與 TC-7（完整生命週期回放）全數 PASS。

---

### 里程碑四：5000ms 在途請求冷卻窗口與彈窗抗震盪設計 (AD-169)

1. **舊在途請求競爭抖動 (In-Flight 401 Thrashing)**：
   - 使用者在彈窗輸入正確金鑰完成重錨定後，彈窗關閉。但在重錨定前發出、攜帶舊 Token 的背景請求陸續返回 401。
   - 舊版程式碼無恢復時間標記，該 401 會再次觸發 `triggerReauthPrompt()`，導致剛關閉的彈窗立刻重新彈出。
2. **冷卻吸收窗口實作**：
   - 在 `frontend/lib/auth-session.ts` 引入 `let lastRestoredAt = 0;`。
   - 在 `triggerReauthPrompt` 入口設置守衛：`if (Date.now() - lastRestoredAt < 5000) return;`。
   - 在 `reanchorSessionWithKey` 成功寫入 LocalStorage 後打上時間戳記 `lastRestoredAt = Date.now();`。
3. **測試覆蓋**：
   - `frontend/__tests__/in-place-reauth-resilience.test.ts` TC-10 驗證 5 秒內在途 401 被靜默吸收，廣播次數維持為 1，有效消解 Modal Thrashing。

---

### 里程碑五：全域安全帳本確定性守恆校驗與台帳修復 (FP-086)

1. **台帳數學守恆守護**：
   - 執行後端全量測試時，`test_root_hygiene_sentinel.py::test_deterministic_security_ledger_invariants` 抓出 `len(targets) (230) != total_targets (226)`。
   - 追查發現前期增補時有 3 筆 target ID 重複（`outbox_eviction_on_auth_desync`, `in_place_reauth_and_wrong_user_hazard`, `event_flood_and_modal_thrashing`）。
2. **確定性去重與校驗通過**：
   - 執行腳本以 ID 去重並重新計算統計：
     - `total_targets`: 227
     - `audited_targets`: 227
     - `verified_vulnerabilities`: 51
     - `remediated_vulnerabilities`: 40
     - `dismissed_hypotheses`: 136
   - 執行 `python scripts/validate_security_ledger.py` 輸出 `🟢 [LEDGER GUARD] Verified 227 targets`，測試恢復 100% 綠燈。

---

## 🏛️ 架構決策記錄 (Architecture Decisions)

- **AD-166: 伺服器端先驗身分斷言與傳輸層零洩漏架構 (Zero-Wire-Leak Architecture)**
  - Context: 舊版後端收到有效 recovery key 即簽發 JWT，客戶端收到後才攔截，導致 JWT 在 Network Tab 洩漏。
  - Decision: `SessionRequest` 擴充 `expected_user_id`；後端在資料庫檢索成功後，在簽發 JWT 前執行身分斷言，不符則直接 401，Response Body 零 Token、零身分傳輸。
  - Status: Implemented & Verified in `backend/routers/auth.py`.

- **AD-167: 統一常數回傳與枚舉預言機消解 (Constant-Error Oracle Defense)**
  - Context: 提示「此引繼碼屬於另一個帳號」向探測者證實引繼碼之存在性。
  - Decision: 全鏈路統一使用常數 `"引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。"`。
  - Status: Implemented in `backend/routers/auth.py`, `frontend/lib/auth-session.ts`, `frontend/components/auth/session-reauth-modal.tsx`.

- **AD-168: 離線寄件匣物理凍結與突變保全 (Outbox 401 Freeze & Data Preservation)**
  - Context: 401 錯誤重試 3 次導致 dequeue 丟失離線行程。
  - Decision: 遭遇 401 立即 `SyncEngineControl.pause()` 並退出回放迴圈，重錨定後 `resume()` 回放。
  - Status: Implemented in `frontend/lib/sync-engine.ts`, `frontend/lib/sync-hooks.ts`.

- **AD-169: 5000ms 在途請求吸收窗口 (Post-Restoration Grace Window)**
  - Context: 重錨定後在途舊 401 請求反覆喚醒彈窗。
  - Decision: 設置 `lastRestoredAt`，重錨定後 5000ms 內靜音在途 401。
  - Status: Implemented in `frontend/lib/auth-session.ts`.

- **AD-170: 登出破壞性清除防護警告 (Destructive Logout Guard)**
  - Context: 點擊登出清空 LocalStorage 會抹除離線未同步資料。
  - Decision: 在 `profile-view.tsx` 加入顯式警告對話框，同步凍結時提示金鑰待驗證。
  - Status: Implemented in `frontend/components/views/profile-view.tsx`.

---

## 🛡️ 失敗路徑與避坑指南 (Failed Paths)

- **FP-085: ESLint 寬鬆型別與未引用宣告**
  - Symptom: 在 `in-place-reauth-resilience.test.ts` 中使用了 `any` 與未引用的 `MockFetchOptions`，觸發 ESLint 警報。
  - Lesson: 測試代碼亦應導入嚴格型別介面 (`CapturedPayload`, `MockServerBody`) 與顯式收窄斷言，維持 0 錯誤底線。

- **FP-086: 安全台帳統計數字未嚴格守恆 (Ledger Conservation Violation)**
  - Symptom: 台帳手動增補項目時長度為 230，但 statistics 填寫 226，且有 3 筆重複 ID，導致 `validate_security_ledger.py` 與 `test_root_hygiene_sentinel.py` 報錯。
  - Lesson: 台帳增補必須依賴確定性 Python 腳本進行 deduplicate 與精確統計，確保 `total == audited == (verified + remediated + dismissed)`。

---

### 里程碑六：Dependabot 容器崩潰法醫學診斷與零依賴漏洞治理 (Dependabot Crash Forensic & Zero-Vulnerability Resolution, AD-171)

1. **事故現象與日誌溯源**：
   - GitHub Dependabot 在執行 `/frontend` 依賴動態更新時回報容器崩潰：`Command failed with exit code 1: /bin/sh -c $DEPENDABOT_HOME/dependabot-updater/bin/run update_files`，任務標記為 Failure。
2. **法醫學根因**：
   - GitHub 安全審計通報了 5 項安全漏洞（`next`, `dompurify`, `vite`, `@vitest/mocker`）。
   - 在 `package-lock.json` 中，根開發依賴 `vitest@4.1.11` 內部對 `@vitest/mocker` 實施了絕對版本相等約束（`"@vitest/mocker": "4.1.11"`）。
   - 當 Dependabot 的 `update_files` 容器指令試圖單獨在 Lockfile 中將間接依賴 `@vitest/mocker` 升級至 `4.1.12`，而未同時升級根層 `vitest` 時，npm 解析器引發約束破壞與 Exit Code 1 崩潰。
3. **治理與閉環策略**：
   - **根層升級**：將 `frontend/package.json` 中的 `next` 升級至 `^16.4.3`，`vitest` 升級至 `^4.1.12`，帶動內部所有 `@vitest/*` 組件整體躍升至安全基準。
   - **overrides 原地增量合併**：在 `package.json` 的 `overrides` 中增補 `"dompurify": "^3.4.17"` 與 `"vite": "^7.3.7"`，杜絕底層依賴重複產生漏洞。
   - **建立確定性配置**：新建 `.github/dependabot.yml`，明確宣告 `/frontend` 與 `/backend` 之套件生態系與分組規則。
4. **驗收成效**：
   - `npm audit`：由 5 項漏洞（2 Moderate, 1 High, 2 Critical）完全降至 **0 vulnerabilities**。
   - `npm ls --depth=0`：退出代碼 0，無任何 `ELSPROBLEMS`。
   - `next build`：Turbopack 產品級建置成功，10/10 靜態頁面生成完畢。


---

### 里程碑七：生產端本機憑證死鎖消解與十秒防轟炸熔斷 (Stale Token Latching & Anti-Storm Cooldown, AD-172)

1. **事故現象與 DevTools 遙測**：
   - 生產端 `https://www.tabijiapp.com` 在 `requestIdleCallback` 背景執行 `fetchLatestRecoveryKey()` 存取 `/api/auth/credential` 時，DevTools Console 跳出 `GET /api/auth/credential 401 (Unauthorized)`。
2. **病理剖析（本機憑證死鎖 Stale Token Latching）**：
   - 伺服器端帳號已輪替提升憑證版本號 (`session.token_version < db_ver`)，依法拒絕歷史憑證。
   - 舊版前端在收到 401 後僅返回 `null`，未主動從 `localStorage` 清除作廢的舊 Token。
   - 導致瀏覽器在每次頁面喚醒、閒置或網路重連時，反覆掏出已作廢的舊 Token 發送請求，造成控制台紅字噪音與無效網路開銷。
3. **治理與閉環實作**：
   - **401 物理清除（Physical Stale Token Purge）**：`fetchLatestRecoveryKey()` 在 `res.status === 401` 時立即執行 `localStorage.removeItem(TOKEN_KEY)`，阻斷死票撞門。
   - **10 秒換票冷卻保護（Anti-Storm Cooldown）**：在 `ensureValidSession()` 中引入 `lastExchangeFailedAt`，在 401 失敗後 10 秒內短路返回 `null`，阻絕 SWR 密集重試雪崩。
   - **全新訪客重置逃生門（Fresh Anonymous Session Reset）**：實作 `resetAndStartFreshSession()`，並在 `SessionReauthModal` 增設「重設為全新帳號」按鈕，為引繼碼徹底丟失之使用者提供原地一鍵自癒逃生通道。
4. **測試驗收**：
   - `auth-session-resilience.test.ts` 新增 TC-10（401 觸發重認證）與 TC-11（10 秒冷卻防轟炸）。
   - `session-reauth-modal.test.tsx` 新增 TC-4（全新帳號重置流程）與 TC-5（錯誤容錯）。
   - 前端 568 測試、後端 298 測試 100% 通過。

---

## 🎯 明日核心衝刺目標 (Next Steps)
1. 監控 Dependabot 於 GitHub 上的分組更新表現，確保 PR #22 自動閉合且零容器報錯。
2. 持續監控 PWA 離線環境下的長生命週期同步健康度與生產端 Console 純淨度。

---

## 🧬 Machine-Executable Invariant Rules
```json
[
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-001",
    "title": "Server-Side Expected User ID Assertion Before JWT Issuance",
    "content": "In /api/auth/session, when expected_user_id is provided by the client, the backend must assert user['id'].strip().lower() == expected_user_id.strip().lower() BEFORE calling create_session_jwt. Mismatched identities must return 401 with zero tokens serialized in response body."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-002",
    "title": "Constant Error String for Identity Oracle Suppression",
    "content": "All recovery key verification failures (format invalid, non-existent key, hash mismatch, expected_user_id mismatch) across backend and frontend must output the identical uniform constant string: '引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。' Never reveal 'belongs to another account'."
  },
  {
    "domain": "offline_pwa",
    "type": "INVARIANT_RULE",
    "id": "INV-OFFLINE-001",
    "title": "Outbox 401 Physical Freeze and Dequeue Protection",
    "content": "When useBackgroundSync encounters a 401 Unauthorized during mutation replay, it must immediately call SyncEngineControl.pause() and break out of the replay loop without incrementing retryCount and without dequeuing the mutation."
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-003",
    "title": "Post-Restoration Grace Window Against Modal Thrashing",
    "content": "Client-side triggerReauthPrompt must enforce a 5000ms grace cooldown based on lastRestoredAt timestamp to absorb in-flight stale 401 responses fired before re-anchoring, preventing modal reopening thrashing."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-019",
    "title": "Pinned Transitive Package Alignment in Dependabot & npm Overrides",
    "content": "When direct dependencies strictly pin internal sub-packages (e.g. vitest strictly pinning @vitest/mocker), Dependabot single-package transitive updates fail with exit code 1. Root dependencies must be bumped in unison with npm overrides incrementally merged to guarantee 0 vulnerabilities and 0 container resolution crashes."
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-004",
    "title": "Stale Token Purge on Background Credential 401 & 10s Exchange Cooldown",
    "content": "When background vault synchronization (/api/auth/credential) returns 401 Unauthorized, client must immediately purge stale TOKEN_KEY from localStorage. In ensureValidSession, a 10000ms cooldown (lastExchangeFailedAt) must be enforced upon 401 to prevent SWR storm hammering."
  }
]
```
