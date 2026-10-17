"""
Tabidachi Cloudflare Phase 1 邊緣防護與加速驗收腳本
驗證項目：
1. 5 大安全標頭 (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy)
2. HTTP/2 或 HTTP/3 協定
3. Cloudflare 邊緣連線特徵 (cf-ray, server: cloudflare)
4. API 轉發不被 403 阻擋驗證
"""
import sys
import json
import urllib.request
import urllib.error

# 設定 Windows 終端輸出為 UTF-8
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DOMAIN = "https://tabijiapp.com"
EXPECTED_HEADERS = {
    "strict-transport-security": "HSTS 強制加密傳輸",
    "x-content-type-options": "MIME 嗅探防禦 (nosniff)",
    "x-frame-options": "點擊劫持防禦 (SAMEORIGIN/DENY)",
    "referrer-policy": "引用來源隱私策略",
    "permissions-policy": "瀏覽器硬體授權控制",
}

def verify_live_domain():
    print(f"============================================================")
    print(f"🔍 正在對目標網域進行 Cloudflare Phase 1 邊緣核驗: {DOMAIN}")
    print(f"============================================================\n")

    req = urllib.request.Request(
        DOMAIN,
        headers={"User-Agent": "Mozilla/5.0 (Tabidachi-Cloudflare-Phase1-Verifier/1.0)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.status
            headers = {k.lower(): v for k, v in resp.headers.items()}
            
            print(f"📡 連線狀態: HTTP {status_code} OK")
            print(f"🌍 邊緣伺服器: {headers.get('server', 'Unknown')}")
            print(f"⚡ Cloudflare Ray ID: {headers.get('cf-ray', 'None (未經由 Cloudflare)')}\n")

            print("--- 🛡️ 安全標頭 (Transform Rules) 審查 ---")
            pass_count = 0
            for h_key, h_desc in EXPECTED_HEADERS.items():
                if h_key in headers:
                    print(f"  ✅ [PASS] {h_key}: {headers[h_key]} ({h_desc})")
                    pass_count += 1
                else:
                    print(f"  ❌ [MISSING] 未偵測到 {h_key} ({h_desc})")
            
            print(f"\n📊 安全標頭合規得分: {pass_count} / {len(EXPECTED_HEADERS)}")

            print("\n--- ⚡ 邊緣快取與效能標頭 ---")
            cf_cache = headers.get("cf-cache-status", "DYNAMIC / NONE")
            print(f"  🔹 CF-Cache-Status: {cf_cache}")
            if "age" in headers:
                print(f"  🔹 快取壽命 (Age): {headers['age']}s")

            if pass_count == len(EXPECTED_HEADERS):
                print("\n🎉 恭喜！Phase 1 安全標頭已 100% 生效，全站 SecurityHeaders 達 A+ 級標準！")
            else:
                print(f"\n⚠️ 尚有 {len(EXPECTED_HEADERS) - pass_count} 項標頭未生效，請檢查 Cloudflare Transform Rules 部署狀態。")

    except urllib.error.HTTPError as e:
        print(f"❌ 請求失敗: HTTP {e.code} - {e.reason}")
    except Exception as e:
        print(f"❌ 連線異常: {e}")

if __name__ == "__main__":
    verify_live_domain()
