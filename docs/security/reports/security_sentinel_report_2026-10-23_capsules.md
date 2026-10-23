# 🛡️ Security Sentinel 對抗式沙盒審計報告 (時光膠囊即時協同與隱私防護)

> **審計日期**: 2026-10-23  
> **審計模式**: `sentinel-agy-adversarial` (Cloudflare 6-Phase Ledger ✕ Google Mantis Patch ✕ agy.exe CLI 物理隔離沙盒)  
> **執法標準**: L0 人類主權憲法 (只回報，交由人類決策；未經核准不碰原始碼)  
> **驗證狀態**: 5 個目標平行審查完成 (1 個 Confirm 漏洞、4 個 Dismiss 釐清，In-Memory PoC 4/4 PASSED)

---

## 執行摘要 (Executive Summary)

| 審計目標 | 信任邊界 | 攻擊/缺陷向量 | Sentinel 裁決 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| [`frontend/lib/idb-storage.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/idb-storage.ts) | `browser_local` | 共用裝置多帳號快照竊密 (`storage_isolation`) | **CONFIRMED** | 🚨 待修復 |
| [`frontend/lib/hooks/useTripRealtime.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/hooks/useTripRealtime.ts) | `browser_to_edge` | Supabase RLS WAL 靜默抑制與進度脫節 | **DISMISSED** | 💡 架構確認 |
| [`frontend/components/itinerary/PolaroidCapsuleModal.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/PolaroidCapsuleModal.tsx) | `browser_to_edge` | WebSocket 封包廣播明文竊聽 (`data_leakage`) | **DISMISSED** | 💡 架構確認 |
| [`backend/routers/capsules.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/capsules.py) | `authenticated_to_internal` | 提前破印解鎖與 BOLA 越權攻擊 | **DISMISSED** | 💡 功能增強 |
| [`frontend/components/views/itinerary-view.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/itinerary-view.tsx) | `browser_local` | 破印盛典非同步競爭與重入震盪 | **DISMISSED** | 💡 狀態等冪 |

---

## 漏洞深度實證與 In-Memory PoC

### 🚨 SEC-CAPSULE-01: L0 LocalStorage 未帶 `userId` 命名空間引發共用裝置跨帳號竊密 (CONFIRMED)
- **攻擊場景 (Attack Scenario)**：
  在旅行場景中，兩位旅伴常共用同一台平板或由其中一人手機交替登入。若時光膠囊快照儲存僅以 `tripId` 為鍵（`tabiji_capsule_sync_${tripId}`），旅伴 A 封存的真心話與私密拍立得在退出登入後仍殘留於本機 `localStorage`。旅伴 B 登入同台設備即可在離線狀態下繞過後端 RLS 限制直接窺探 A 的秘密。
- **In-Memory PoC 驗證實證 ([test_capsules_realtime_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_capsules_realtime_sentinel_poc.py#L140-L177))**：
  ```bash
  pytest backend/tests/test_capsules_realtime_sentinel_poc.py -v -k "test_tc3"
  # 結果：PASSED (證實單鍵模式下 Bob 成功讀出 Alice 機密；雙鍵模式 tabiji_capsule_sync_${tripId}_${userId} 達成物理隔離)
  ```

---

## 💡 架構釐清與邊界守衛 (Dismissed Hypotheses Analysis)

1. **Supabase RLS WAL 靜默抑制 (`useTripRealtime.ts`)**：
   - Sentinel 裁決確認：現有程式碼未將 `trip_capsule_entries` 掛載至 `postgres_changes`，因此未引發執行期錯誤。然而依據 RLS 規則，非作者旅伴在封存階段會被資料庫層物理過濾，**這在架構上證明了 Phoenix Broadcast (`capsule:update`) 是推動進度的唯一通道**。
2. **客戶端廣播明文洩漏 (`PolaroidCapsuleModal.tsx`)**：
   - 現有組件僅透過 HTTP POST 調用後端，無客戶端廣播。Sentinel 確立了**「零明文洩漏守衛」**：即未來接入廣播時，酬載絕對不可包含 `content` 與 `photo_url`，僅傳遞 `{ day_number, author_id, action: "sealed" }`。
3. **提前破印解鎖端點 (`backend/routers/capsules.py`)**：
   - 現行後端僅依賴目的地 UTC 時間鎖，無手動解鎖端點。此非既有漏洞，而是為因應「最後一晚告別晚宴提前破印」之新增業務需求，候選補丁已補齊 `POST /api/trips/{trip_id}/capsules/unlock` 並嚴格校驗行程成員身份以抵禦 BOLA。
4. **盛典重入防衛 (`itinerary-view.tsx`)**：
   - React 布林狀態設定函式 `setIsCapsuleCeremonyOpen(true)` 具備等冪性，但為防止非同步廣播事件導致翻牌卡片重置，已於補丁中加入 `!isCapsuleCeremonyOpen` 防衛。

---

## 候選補丁與精確區塊替換 (Mantis Candidate Patch)

完整的候選補丁已存放於 [`docs/security/patch_candidate_capsules_realtime_2026-10-23.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_capsules_realtime_2026-10-23.diff)。

### 精確區塊對應清單 (Block Replacement Instructions)

#### 1. 檔案：`frontend/lib/idb-storage.ts`
- **原職責**：L0/L1/L2 快照存取。
- **替換內容**：追加雙維度隔離之 `saveTripCapsuleSnapshot` 與 `getTripCapsuleSnapshotSync`（以 `tripId + userId` 雙鍵命名）。

#### 2. 檔案：`frontend/lib/hooks/useTripRealtime.ts`
- **原職責**：行程即時協同與廣播。
- **替換內容**：擴充 `broadcastTripEvent` 型別加入 `"capsule:update" | "capsule:unveil"`；於 `channel.on("broadcast")` 區塊加入膠囊 Tuple Predicate 刷新邏輯。

#### 3. 檔案：`frontend/components/itinerary/PolaroidCapsuleModal.tsx`
- **原職責**：膠囊心得輸入彈窗。
- **替換內容**：在 `capsulesApi.submit` 成功後調用 `broadcastTripEvent`，**嚴格遵守零明文洩漏守衛**。

#### 4. 檔案：`backend/routers/capsules.py`
- **原職責**：膠囊後端路由。
- **替換內容**：追加 `POST /api/trips/{trip_id}/capsules/unlock` 提前解鎖端點，嚴格實施成員權限驗證。

---

## 人類閘門移交 (Human Gate Handover)
依據 L0 憲法，全套對抗審計已在沙盒完成，In-Memory PoC 全數通過，本報告與補丁僅供審查。
等待 Ryan 確認批准後，方可由 `@dev` 執行實體程式碼變更與 `@qa` 測試驗收。
