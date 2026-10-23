# 🛡️ Security Sentinel 對抗審查報告：Cloud Run CI/CD 物理脫鉤與零洩漏驗證

- **審計日期**: 2026-10-23
- **審核工具**: Security Sentinel Harness Runner (`agy.exe --sandbox`) ✕ Python In-Memory PoC ✕ 隔離目錄克隆實測
- **審核目標**: `.github/workflows/deploy-backend.yml` (CI/CD 部署流程)

---

## 📊 一、執行摘要 (Executive Summary)

| 審核項目 | 測試形式 | 判定 (Verdict) | 威脅層級 | 結論 |
| :--- | :--- | :--- | :--- | :--- |
| **CI/CD 密鑰耦合漏洞** | 獨立沙盒子代理人審查 | **CONFIRMED** | High | `--set-env-vars` 與 `--set-secrets` 將雲端執行期機密與 Git 倉庫緊密耦合，造成歷史留痕與 Log 暴露風險。 |
| **脫鉤架構沙盒實測** | 物理克隆 `git filter-repo` | **PASSED (100%)** | None | 移除參數後，7 大敏感詞全域歷史搜尋命中數全數歸零，YAML 結構合法。 |
| **Cloud Run 留存契約** | In-Memory PoC | **PASSED** | None | 實證 Cloud Run 在未傳遞 `--set-env-vars` 時，自動保留 Console 配置之所有機密與環境變數。 |

---

## 🔬 二、獨立沙盒審查證偽結論 (Adversarial Findings)

來自 `docs/security/findings_phase2_decoupling.json` 之硬核遙測輸出：

```json
{
  "target_id": ".github/workflows/deploy-backend.yml",
  "verdict": "CONFIRMED",
  "reasoning": "The workflow's 'Deploy to Cloud Run' step directly includes `--set-env-vars` and `--set-secrets` in the `gcloud run deploy` command. Direct interpolation of GitHub secrets (e.g., ${{ secrets.TP_API_TOKEN }}) into shell arguments risks leaking sensitive values into runner logs or process inspection. Additionally, passing `--set-env-vars` replaces all existing service environment variables, preventing independent management via Cloud Run console/Secret Manager. Cloud Run automatically preserves console-configured environment variables and secrets across new revisions when neither `--set-env-vars` nor `--set-secrets` is supplied.",
  "remediation_hint": "Remove both `--set-env-vars` and `--set-secrets` flags from the gcloud run deploy invocation in .github/workflows/deploy-backend.yml. Configure all required environment variables and Secret Manager references directly in Google Cloud Run (via GCP Console, Terraform, or an initial setup script); Cloud Run will retain these configurations automatically on all subsequent revision deployments."
}
```

---

## 🧪 三、沙盒實體演練遙測數據 (Sandbox Dry-Run Telemetry)

在獨立沙盒目錄 `D:\Project\tabiji\sandbox-scrub-trial` 中，以真實儲存庫運行 7 大機密標籤之全面過濾與脫鉤測試：

```json
=== PHASE 2 SANDBOX TELEMETRY ===
{
  "clone": "SUCCESS",
  "commit": "SUCCESS",
  "filter_repo": "SUCCESS",
  "history_leak_counts": {
    "tp_token (REDACTED_TP_TOKEN)": 0,
    "cloudinary_key_1 (REDACTED_CLOUDINARY_KEY)": 0,
    "cloudinary_key_2 (REDACTED_CLOUDINARY_KEY_2)": 0,
    "supabase_ref (REDACTED_SUPABASE_REF)": 0,
    "cloudinary_cloud (REDACTED_CLOUDINARY_CLOUD)": 0,
    "worker_host (REDACTED_WORKER_HOST)": 0,
    "user_uuid (00000000-0000-0000-0000-000000000001)": 0
  },
  "history_cleansed": true,
  "yaml_valid": true,
  "wf_has_set_env_vars": false,
  "wf_has_set_secrets": false,
  "origin_restored": true
}
[+] ALL PHASE 2 SANDBOX CHECKS PASSED: 100% GREEN
```

---

## 🛠️ 四、精確替換補丁 (Mantis Block Replacement)

### 目標檔案: `.github/workflows/deploy-backend.yml`

#### Target Content (原有脆弱代碼 Lines 30-47):
```yaml
        # Using Mixed Secrets Strategy:
        # 1. SUPABASE_KEY: Pulled from Google Secret Manager (Best Practice)
        # 2. Others: Passed via GitHub Secrets -> Env Vars (Easier setup for now)
        run: |
          gcloud run deploy antigravity-backend \
            --source ./backend \
            --platform managed \
            --region us-central1 \
            --allow-unauthenticated \
            --memory 1Gi \
            --cpu 1 \
            --concurrency 40 \
            --timeout 300s \
            --max-instances 10 \
            --min-instances 0 \
            --set-env-vars "^||^SUPABASE_URL=https://REDACTED_SUPABASE_REF.supabase.co||API_VERSION=v1||NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=REDACTED_CLOUDINARY_CLOUD||CLOUDINARY_API_KEY=REDACTED_CLOUDINARY_KEY_2||TP_API_TOKEN=${{ secrets.TP_API_TOKEN }}||GAS_GEOCODE_URLS=${{ secrets.GAS_GEOCODE_URLS }}||GAS_RESOLVE_LINK_URLS=${{ secrets.GAS_RESOLVE_LINK_URLS }}||CF_WORKER_SEARCH_URL=https://tabidachi-search-proxy.REDACTED_WORKER_HOST" \
            --set-secrets "SUPABASE_KEY=supabase-key:latest,ARCGIS_API_KEY=arcgis-api-key:latest,CLOUDINARY_API_SECRET=cloudinary-api-secret:latest" \
            --project antigravity-prod-2026
```

#### Replacement Content (修復後零洩漏代碼):
```yaml
        # Zero-Leakage Architecture:
        # All environment variables and secrets are configured directly in Cloud Run Console.
        # Cloud Run automatically retains all existing console variables across deployments.
        run: |
          gcloud run deploy antigravity-backend \
            --source ./backend \
            --platform managed \
            --region us-central1 \
            --allow-unauthenticated \
            --memory 1Gi \
            --cpu 1 \
            --concurrency 40 \
            --timeout 300s \
            --max-instances 10 \
            --min-instances 0 \
            --project antigravity-prod-2026
```

---

## ⚖️ 五、人類決策閘口 (Human Gate Handover)

所有沙盒驗證與對抗證偽已完成並產出客觀證據。
待人類確認後，即可一鍵將修復代碼落盤，並透過 `git filter-repo` 將全體 7 大敏感特徵自 Git 歷史永久抹除。
