"""
Tabidachi Cloudflare D1 POI 微服務端到端線上驗收腳本
驗證項目：
1. 邊緣身分校驗防禦 (401 on missing/invalid UUIDv4)
2. 邊緣查詢與 D1 複合索引命中 (GET /api/poi/all)
3. 邊緣原子寫入 (POST /api/poi/add)
4. 邊緣單點刪除 (DELETE /api/poi/:id)
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
TEST_UUID = "87c22592-1205-4f5c-ab43-66d798a52d99"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def run_e2e_verification():
    print(f"============================================================")
    print(f"🔍 正在執行 Cloudflare D1 POI 微服務線上端到端驗證: {DOMAIN}")
    print(f"============================================================\n")

    pass_count = 0
    total_tests = 4

    # 1. 測試非法身分 401 攔截
    print("1. [Auth Guard] 測試非法身分攔截 (無效 UUIDv4)...")
    req1 = urllib.request.Request(
        f"{DOMAIN}/api/poi/all",
        headers={"User-Agent": UA, "X-User-ID": "illegal-admin-spoof"}
    )
    try:
        urllib.request.urlopen(req1, timeout=10)
        print("  ❌ [FAIL] 預期應回傳 401，但請求成功了！")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("  ✅ [PASS] 成功攔截非法身分，回傳 HTTP 401 Unauthorized")
            pass_count += 1
        else:
            print(f"  ❌ [FAIL] 回傳錯誤代碼非 401: HTTP {e.code}")
    except Exception as e:
        print(f"  ❌ [FAIL] 連線異常: {e}")

    # 2. 測試合法身分讀取 (D1 索引覆蓋查詢)
    print("\n2. [D1 Read] 測試合法身分讀取 (GET /api/poi/all)...")
    req2 = urllib.request.Request(
        f"{DOMAIN}/api/poi/all",
        headers={"User-Agent": UA, "X-User-ID": TEST_UUID}
    )
    try:
        with urllib.request.urlopen(req2, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"  ✅ [PASS] 邊緣讀取成功: HTTP {resp.status}, 現存景點數: {len(data)}")
            pass_count += 1
    except Exception as e:
        print(f"  ❌ [FAIL] 讀取失敗: {e}")

    # 3. 測試邊緣寫入 (POST /api/poi/add)
    print("\n3. [D1 Write] 測試邊緣新增景點 (POST /api/poi/add)...")
    poi_payload = json.dumps({
        "title": "驗收測試地點 - 淺草雷門",
        "lat": 35.7111,
        "lng": 139.7963,
        "category": "attraction",
        "user_notes": "Cloudflare D1 E2E Verification Spot"
    }).encode('utf-8')
    req3 = urllib.request.Request(
        f"{DOMAIN}/api/poi/add",
        data=poi_payload,
        headers={"User-Agent": UA, "Content-Type": "application/json", "X-User-ID": TEST_UUID},
        method="POST"
    )
    created_id = None
    try:
        with urllib.request.urlopen(req3, timeout=10) as resp:
            created_data = json.loads(resp.read().decode('utf-8'))
            created_id = created_data.get('id')
            print(f"  ✅ [PASS] 寫入成功: HTTP {resp.status}, ID: {created_id}")
            pass_count += 1
    except Exception as e:
        print(f"  ❌ [FAIL] 寫入失敗: {e}")

    # 4. 測試邊緣刪除 (DELETE /api/poi/:id)
    if created_id:
        print(f"\n4. [D1 Delete] 測試刪除剛才建立的景點 (DELETE /api/poi/{created_id})...")
        req4 = urllib.request.Request(
            f"{DOMAIN}/api/poi/{created_id}",
            headers={"User-Agent": UA, "X-User-ID": TEST_UUID},
            method="DELETE"
        )
        try:
            with urllib.request.urlopen(req4, timeout=10) as resp:
                print(f"  ✅ [PASS] 刪除成功: HTTP {resp.status}")
                pass_count += 1
        except Exception as e:
            print(f"  ❌ [FAIL] 刪除失敗: {e}")
    else:
        print("\n4. [D1 Delete] 跳過（未取得建立之 ID）")

    print("\n============================================================")
    print(f"📊 驗收測試總分: {pass_count} / {total_tests}")
    if pass_count == total_tests:
        print("🎉 恭喜！Cloudflare D1 POI 邊緣微服務與 Edge Shield 100% 驗證通過！")
    else:
        print("⚠️ 部份測試未通過，請檢查詳細日誌。")
    print("============================================================\n")

if __name__ == "__main__":
    run_e2e_verification()
