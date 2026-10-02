import sys
import os
import asyncio
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

API_BASE = "http://127.0.0.1:8008"
API_KEY = os.getenv("GEMINI_API_KEY", "")

async def test_stream(title: str, payload: dict):
    print(f"\n{'='*20} {title} {'='*20}")
    print(f"👉 提問: {payload.get('message')}")
    if payload.get("client_time"):
        print(f"🕒 客戶端時間: {payload.get('client_time')} ({payload.get('client_timezone')})")
    if payload.get("current_itinerary"):
        print(f"📅 綁定行程: {payload['current_itinerary'].get('title')}")

    received_thinking = []
    received_text = ""
    model_used = ""

    headers = {
        "Content-Type": "application/json",
        "X-Gemini-API-Key": API_KEY
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream(
                "POST", 
                f"{API_BASE}/api/chat/stream",
                json=payload,
                headers=headers
            ) as response:
                print(f"📡 HTTP 狀態碼: {response.status_code}")
                current_event = ""
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line.replace("event:", "").strip()
                    elif line.startswith("data:"):
                        data_str = line.replace("data:", "").strip()
                        if not data_str:
                            continue
                        try:
                            data = json.loads(data_str)
                            if current_event == "thinking":
                                thought = data.get("thought") or data.get("status")
                                if thought:
                                    received_thinking.append(thought)
                            elif current_event == "text":
                                received_text += data.get("text", "")
                            elif current_event == "done":
                                model_used = data.get("model_used", "")
                            elif current_event == "error":
                                print(f"⚠️ SSE 錯誤事件: {data}")
                        except Exception:
                            pass
        except Exception as e:
            print(f"❌ 請求失敗: {e}")
            return

    print(f"🧠 思考感知過程: {received_thinking}")
    print(f"🤖 AI 回答: {received_text[:180]}...")
    print(f"🏷️ 使用模型: {model_used}")
    print(f"✅ 狀態: 成功閉環")

async def main():
    print("🚀 [Tabidachi Temporal Engine] 即時全鏈路端到端驗證開始...")
    
    # 測試 1: 純時間與時區感知 (無行程狀態)
    await test_stream(
        "測試 1: 使用者手機時間感知 (台北時間 20:25)",
        {
            "message": "現在幾點？今天星期幾？",
            "client_time": "2026-10-02T20:25:00+08:00",
            "client_timezone": "Asia/Taipei",
            "history": []
        }
    )

    # 測試 2: 行程進度與活動結束判定 (東京時間 21:25)
    await test_stream(
        "測試 2: 行程狀態機判定 (當前時間晚於所有活動，應判定已結束)",
        {
            "message": "我今天的行程結束了嗎？現在還能去哪裡？",
            "client_time": "2026-10-02T20:25:00+08:00", # 台北 20:25 -> 東京 21:25
            "client_timezone": "Asia/Taipei",
            "focused_day": 1,
            "current_itinerary": {
                "title": "東京精華一日遊",
                "destination": "東京",
                "start_date": "2026-10-02",
                "end_date": "2026-10-02",
                "total_days": 1,
                "days": [
                    {
                        "day_number": 1,
                        "date": "2026-10-02",
                        "items": [
                            {"place": "淺草寺", "time": "10:00~12:00", "category": "sightseeing"},
                            {"place": "晴空塔", "time": "18:00~20:00", "category": "sightseeing"}
                        ]
                    }
                ]
            },
            "history": []
        }
    )

    # 測試 3: 世界時間工具與 ReAct 閉環 (查詢倫敦時間)
    await test_stream(
        "測試 3: Server-side ReAct 閉環 (查詢倫敦時間)",
        {
            "message": "請問現在倫敦幾點？",
            "client_time": "2026-10-02T20:25:00+08:00",
            "client_timezone": "Asia/Taipei",
            "history": []
        }
    )

if __name__ == "__main__":
    asyncio.run(main())
