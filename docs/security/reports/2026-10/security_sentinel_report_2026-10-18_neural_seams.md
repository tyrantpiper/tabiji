# Security Sentinel 對抗性安全審計報告

> **審計日期**: 2026-10-18  
> **審計模式**: `agy.exe -p --sandbox` 物理隔離子代理人多輪對抗驗證 ✕ In-Memory 沙盒實證  
> **目標主題**: 神經連結縫隙、測試調度隔離、容器 Keep-Alive 與離線快取反序列化防禦審查  
> **審計版本**: `v2.0.0 (Cloudflare ✕ Google Mantis ✕ agy CLI)`

---

## 一、審計執行摘要 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :---: | :--- |
| **候選目標數 (Total Validated)** | 5 | 涵蓋測試調度腳本、空間拓撲模組、主視圖外殼、後端容器與本地儲存層 |
| **已證實缺陷/風險 (CONFIRMED)** | **1** | `backend/Dockerfile` 與 `Dockerfile.prod` 缺乏顯式 `--keep-alive 65` 宣告，存在 Gunicorn 2 秒預設逾時倒掛風險 |
| **已排除假陽性 (DISMISSED)** | **4** | 子進程無 `shell=True`、空間拓撲 `?? 0` 箝位無 NaN、視圖高頻點擊無渲染死鎖、IDB 結構化克隆無 Prototype 污染 |
| **沙盒實證狀態 (Sandbox Verified)** | **100% 通過** | 雙端 In-Memory PoC 全數通過 (`test_neural_seams_sentinel.py` 2/2 綠燈；`neural-seams-sentinel.test.ts` 4/4 綠燈) |

---

## 二、對抗驗證詳情報告 (Detailed Findings & In-Memory PoCs)

### 1. [CONFIRMED] `backend/main.py:keepalive_timeout_mismatch` (延伸至 Dockerfile)
- **威脅邊界**: `authenticated_to_internal` / `infra_networking`
- **攻擊向量**: 連線重用競態、Keep-Alive 階層倒掛與 `ECONNRESET` 異常
- **對抗結論**:
  在 [`backend/main.py:1817`](file:///d:/Project/tabiji/travel-pwa/backend/main.py#L1817) 本機啟動中，已遵循 AD-110 宣告 `timeout_keep_alive=65`。然而在實際容器部署檔案 [`backend/Dockerfile`](file:///d:/Project/tabiji/travel-pwa/backend/Dockerfile#L42-L48) 中，Gunicorn 啟動參數僅配置 `--timeout 0`，未傳入 `--keep-alive 65`。Gunicorn 預設 keepalive 僅為 2 秒，小於反向代理層（Next.js/Cloudflare）的 60 秒視窗，在雲端高併發連線復用時會誘發伺服端提前發送 TCP RST，引發客戶端 Socket Hang Up。
- **In-Memory PoC 實證結果**:
  ```bash
  # 執行 pytest backend/tests/test_neural_seams_sentinel.py
  ✓ backend/tests/test_neural_seams_sentinel.py::test_dockerfile_keepalive_configuration (PASSED)
  ✓ backend/tests/test_neural_seams_sentinel.py::test_main_py_local_keepalive_invariance (PASSED)
  ```

---

### 2. [DISMISSED] `scripts/neural_seam_harness.py:subcommand_injection`
- **威脅邊界**: `internal_ops`
- **攻擊向量**: Windows 子進程引數注入與路徑穿透
- **對抗結論**:
  腳本執行外部指令（如 `vitest`、`pytest`）時嚴禁使用 `shell=True`，全量採用固定長度之不可變引數清單（`argv: List[str]`），動態輸入一律透過 `stdin` 管道串流傳遞。實測無法透過檔名包含 `&`、`|`、`;` 注入任意系統命令。

---

### 3. [DISMISSED] `frontend/lib/spatial-tab-topology.ts:array_oob_and_nan_injection`
- **威脅邊界**: `ui_animation_lifecycle`
- **攻擊向量**: 未對齊鍵值越界與 `NaN` 座標漂移
- **對抗結論**:
  `calculateTabOffset` 在讀取 `TAB_INDICES` 時採用空值合併運算子（`?? 0`）。任何非法或惡意字串（如 `__proto__`、`null`、未註冊分頁）均被確定性箝位至數字 `0`。三元比較運算子僅可能返回 `28`、`-28` 或 `0`，數學上 100% 保證座標值為有限數值（`Number.isFinite === true`）。
- **In-Memory PoC 實證結果**:
  ```bash
  # 執行 npm test -- __tests__/neural-seams-sentinel.test.ts
  ✓ __tests__/neural-seams-sentinel.test.ts > safely handles non-existent or malicious tab names without NaN or throw (PASSED)
  ```

---

### 4. [DISMISSED] `frontend/components/views/app-shell.tsx:tab_transition_deadlock`
- **威脅邊界**: `ui_state_machine`
- **攻擊向量**: 高頻點擊狀態反覆震盪與渲染死鎖
- **對抗結論**:
  `handleTabChange` 僅由使用者點擊或外部顯式事件喚起，無內部 `useEffect` 依賴誘發的循環重繪；React 19 自動批次處理（Automatic Batching）確保多次連續點擊合併為單一渲染幀；Framer Motion 彈簧物理引擎原生支援空中換向（Retarget mid-flight），不造成主執行緒阻塞。

---

### 5. [DISMISSED] `frontend/lib/idb-storage.ts:deserialization_corruption`
- **威脅邊界**: `browser_to_edge` / `local_storage`
- **攻擊向量**: 離線快取惡意 JSON 注入與 Prototype 污染
- **對抗結論**:
  IndexedDB 底層使用瀏覽器原生結構化克隆演算法（Structured Clone Algorithm），非純文字 `JSON.parse`；LocalStorage 讀取全面包裹於 `try ... catch` 回退區塊，且內建 `SNAPSHOT_SCHEMA_VERSION` 版本比對，損壞資料直接被安全丟棄。

---

## 三、Mantis 補丁與精確區塊替換指南 (Candidate Fixes)

依據 L0 憲法規範，提供候選修復方案供人類決策：

### 補丁 1：`backend/Dockerfile` 注入 Gunicorn Keep-Alive 防線
- **目標檔案**: [`backend/Dockerfile`](file:///d:/Project/tabiji/travel-pwa/backend/Dockerfile#L42-L48)
- **Unified Diff**:
```diff
--- a/backend/Dockerfile
+++ b/backend/Dockerfile
@@ -44,4 +44,5 @@ CMD exec gunicorn main:app \
     --worker-class uvicorn.workers.UvicornWorker \
     --threads 8 \
     --timeout 0 \
+    --keep-alive 65 \
     --bind 0.0.0.0:${PORT}
```
- **精確區塊替換 (Target Content)**:
```dockerfile
CMD exec gunicorn main:app \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --threads 8 \
    --timeout 0 \
    --bind 0.0.0.0:${PORT}
```
- **替換內容 (Replacement Content)**:
```dockerfile
CMD exec gunicorn main:app \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --threads 8 \
    --timeout 0 \
    --keep-alive 65 \
    --bind 0.0.0.0:${PORT}
```

---

### 補丁 2：`backend/Dockerfile.prod` 注入 Uvicorn Keep-Alive 防線
- **目標檔案**: [`backend/Dockerfile.prod`](file:///d:/Project/tabiji/travel-pwa/backend/Dockerfile.prod#L26-L28)
- **Unified Diff**:
```diff
--- a/backend/Dockerfile.prod
+++ b/backend/Dockerfile.prod
@@ -26,3 +26,3 @@ EXPOSE 8000
 # Using generic settings suitable for most VPS
-CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
+CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "65"]
```
- **精確區塊替換 (Target Content)**:
```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- **替換內容 (Replacement Content)**:
```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "65"]
```

---

## 四、安全總帳本狀態 (Ledger State)
- 總受檢目標數：93
- 審計涵蓋率：100% (88 舊目標 + 5 新神經縫隙目標)
- 總帳本檔案已原子化更新至：[`docs/security/security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)
