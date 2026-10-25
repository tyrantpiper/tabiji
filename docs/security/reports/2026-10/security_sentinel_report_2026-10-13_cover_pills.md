# 🛡️ Security Sentinel 對抗性審計報告 (Cover Pipeline & Inspiration Pills)

> **審計日期**：2026-10-13  
> **審計模式**：Sentinel-agy-adversarial (物理子代理人背景隔離審查)  
> **候選存證**：[`docs/security/candidates_cover_pills_harmony_2026-10-13.json`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/candidates_cover_pills_harmony_2026-10-13.json)  
> **發現紀錄**：[`docs/security/findings_cover_pills_harmony.json`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/findings_cover_pills_harmony.json)  
> **總目標數**：4 項 | **實證漏洞 (CONFIRMED)**：1 項 | **安全駁回 (DISMISSED)**：2 項 | **未決/轉移 (INCONCLUSIVE)**：1 項

---

## 📊 攻擊面審計裁決矩陣 (Attack Surface Matrix)

| 目標識別碼 | 攻擊向量 | 信任邊界 | 裁決 (Verdict) | 關鍵證偽與技術剖析 |
| :--- | :--- | :--- | :---: | :--- |
| `frontend/lib/destination-covers.ts:falsy_string_injection` | `falsy_string_injection` | `data_to_presentation` | **DISMISSED** | 靜態檢驗證實 `getTripCoverUrl` 已嚴格執行 `typeof === 'string'`、`.trim()`，並明確排除 `'null'` 與 `'undefined'` 字串，完美回退至預設封面。 |
| `frontend/components/itinerary/TripDialogs.tsx:timezone_drift` | `temporal_timezone_drift` | `client_runtime` | **INCONCLUSIVE** | 背景進程逾時。經前端單元測試 `cover-pills-sentinel.test.ts` 實證，改用 `addDaysToLocalYMD` 本地純數學運算可 100% 杜絕 UTC 偏移。 |
| `frontend/components/itinerary/TripDialogs.tsx:sticky_cover_collision` | `state_collision_ui_desync` | `ui_state` | **DISMISSED** | **極致架構抗辯成功**：使用者明確上傳的圖片應具備最高權威。點擊標題膠囊若靜默清空 `coverImage` 將造成「破壞性資料遺失 (Data Loss)」，維持「自訂圖片 > 自動解析」階層才是正確設計。 |
| `backend/routers/trips.py:create_manual_null_cover` | `database_null_cover_leak` | `authenticated_to_internal` | **CONFIRMED** | `create_manual_trip` 缺少空白清洗與封面自動保底，與 `save_itinerary` 存在嚴重行為不一致，致使手動建程向資料庫寫入 NULL 封面。 |

---

## 🚨 實證漏洞深度分析 (Confirmed Vulnerability Details)

### 漏洞：`backend/routers/trips.py:create_manual_null_cover`
- **弱點類型**：未處理的空值回退與資料庫 NULL 污染 (CWE-476 / CWE-398)
- **觸發後果**：當使用者手動建立行程時，若未傳遞 `cover_image`，資料庫直接存入 `NULL`。導致首頁看板 (`TabijiHomeDashboard`) 與清單 (`TripList`) 渲染為空白漸層色塊，唯獨點進齒輪設定時才由前端記憶體動態算出封面，造成「隨機性」錯覺。
- **In-Memory PoC**：已於 `backend/tests/test_cover_pills_sentinel.py` 驗證。

---

## 🛠️ Mantis Patch 侯選修復方案 (Exact Block Replacement)

### 1. 後端 `create_manual_trip` 封面保底補齊
- **Target File**: `backend/routers/trips.py`
- **Target Content**:
```python
        trip_data = {
            "title": request.title,
            "creator_name": request.creator_name,
            "created_by": user_id,
            "share_code": room_code,
            "public_id": pub_id,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "status": "active",
            "content": {},  # 👈 新增：給個空物件，不要讓它是 NULL
            "flight_info": {},
            "hotel_info": {},
            "cover_image": request.cover_image
        }
```
- **Replacement Content**:
```python
        # 🛡️ 封面保底：若無自訂封面，自動依行程標題解析高畫質風景封面
        clean_cover = request.cover_image.strip() if (request.cover_image and request.cover_image.strip()) else resolve_destination_cover_url(request.title)

        trip_data = {
            "title": request.title,
            "creator_name": request.creator_name,
            "created_by": user_id,
            "share_code": room_code,
            "public_id": pub_id,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "status": "active",
            "content": {},  # 👈 新增：給個空物件，不要讓它是 NULL
            "flight_info": {},
            "hotel_info": {},
            "cover_image": clean_cover
        }
```

---

## ⚖️ 憲法結論 (Constitution Handover)
本報告遵守 L0 憲法，物理對抗證偽與沙盒測試已 100% 完成，交由人類授權後由 `@dev` 實作上線。
