import os
import sys
import time
import json
import base64
import urllib.parse
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading

# Fix Windows cp950 encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("docs/screenshots/frame_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DESKTOP_DIR = Path("D:/User/桌面").resolve()

class DesktopHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DESKTOP_DIR), **kwargs)
    def log_message(self, format, *args):
        pass # 静默

# 啟動本機影片 HTTP 伺服器
PORT = 8899
server = ThreadingHTTPServer(("127.0.0.1", PORT), DesktopHandler)
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
print(f"📡 本機影片串流伺服器已啟動: http://127.0.0.1:{PORT}")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <style>
    body { margin: 0; background: #000; overflow: hidden; }
    video, canvas { display: block; }
  </style>
</head>
<body>
  <video id="v" muted playsinline></video>
  <canvas id="c"></canvas>
</body>
</html>
"""

def analyze_video(filename: str, prefix: str, sample_interval: float = 0.25):
    print(f"\n=======================================================")
    print(f"🎬 開始逐幀分析影片: {filename}")
    print(f"=======================================================")
    
    encoded_name = urllib.parse.quote(filename)
    video_url = f"http://127.0.0.1:{PORT}/{encoded_name}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--allow-file-access-from-files", "--disable-web-security", "--no-sandbox"]
        )
        context = browser.new_context()
        page = context.new_page()
        page.set_content(HTML_TEMPLATE)

        # 載入影片並等待 metadata 與首幀資料就緒
        setup_script = f"""
        async () => {{
            const v = document.getElementById('v');
            v.src = '{video_url}';
            await new Promise((resolve, reject) => {{
                const checkReady = () => {{
                    if (v.videoWidth > 0 && v.videoHeight > 0) {{
                        resolve();
                    }}
                }};
                v.addEventListener('loadeddata', checkReady);
                v.addEventListener('canplay', checkReady);
                v.addEventListener('timeupdate', checkReady);
                v.onerror = (e) => reject('Video load error: ' + (v.error ? v.error.message : 'unknown'));
                // 觸發載入
                v.load();
            }});
            return {{
                duration: v.duration,
                width: v.videoWidth,
                height: v.videoHeight
            }};
        }}
        """
        meta = page.evaluate(setup_script)
        duration = meta["duration"]
        width = meta["width"]
        height = meta["height"]
        print(f"📊 影片元數據: 解析度 {width} x {height}, 總時長 {duration:.2f} 秒")

        current_time = 0.0
        frame_idx = 0
        analysis_log = []

        while current_time <= duration:
            seek_script = f"""
            async () => {{
                const v = document.getElementById('v');
                const c = document.getElementById('c');
                v.currentTime = {current_time};
                await new Promise((resolve) => {{
                    v.onseeked = () => resolve();
                }});
                c.width = v.videoWidth;
                c.height = v.videoHeight;
                const ctx = c.getContext('2d');
                ctx.drawImage(v, 0, 0);

                const W = c.width;
                const H = c.height;

                // 1. 頂部區域 (Top 5% 狀態列)
                const topH = Math.max(20, Math.floor(H * 0.05));
                const topImg = ctx.getImageData(0, 0, W, topH);
                let topR = 0, topG = 0, topB = 0;
                const topPixels = topImg.data.length / 4;
                for (let i = 0; i < topImg.data.length; i += 4) {{
                    topR += topImg.data[i];
                    topG += topImg.data[i+1];
                    topB += topImg.data[i+2];
                }}
                topR = Math.round(topR / topPixels);
                topG = Math.round(topG / topPixels);
                topB = Math.round(topB / topPixels);

                // 2. 底部區域 (Bottom 4% 死區/安全區)
                const botH = Math.max(20, Math.floor(H * 0.04));
                const botY = H - botH;
                const botImg = ctx.getImageData(0, botY, W, botH);
                let botR = 0, botG = 0, botB = 0;
                const botPixels = botImg.data.length / 4;
                for (let i = 0; i < botImg.data.length; i += 4) {{
                    botR += botImg.data[i];
                    botG += botImg.data[i+1];
                    botB += botImg.data[i+2];
                }}
                botR = Math.round(botR / botPixels);
                botG = Math.round(botG / botPixels);
                botB = Math.round(botB / botPixels);

                // 3. 中央區域 (Center 15%)
                const midW = Math.floor(W * 0.2);
                const midH = Math.floor(H * 0.2);
                const midX = Math.floor((W - midW) / 2);
                const midY = Math.floor((H - midH) / 2);
                const midImg = ctx.getImageData(midX, midY, midW, midH);
                let midR = 0, midG = 0, midB = 0;
                const midPixels = midImg.data.length / 4;
                for (let i = 0; i < midImg.data.length; i += 4) {{
                    midR += midImg.data[i];
                    midG += midImg.data[i+1];
                    midB += midImg.data[i+2];
                }}
                midR = Math.round(midR / midPixels);
                midG = Math.round(midG / midPixels);
                midB = Math.round(midB / midPixels);

                return {{
                    time: {current_time},
                    topAvg: [topR, topG, topB],
                    botAvg: [botR, botG, botB],
                    midAvg: [midR, midG, midB],
                    dataUrl: c.toDataURL('image/jpeg', 0.65)
                }};
            }}
            """
            frame_data = page.evaluate(seek_script)
            top = frame_data["topAvg"]
            bot = frame_data["botAvg"]
            mid = frame_data["midAvg"]
            
            is_black_screen = (top[0] < 25 and top[1] < 25 and top[2] < 25 and mid[0] < 25 and mid[1] < 25 and mid[2] < 25)
            is_splash_aurora = (mid[0] > 70 and mid[1] > 35 and mid[2] < 70) 
            is_night_base = (mid[0] < 45 and mid[1] > 30 and mid[2] > 40) 
            is_white_paper_app = (mid[0] > 230 and mid[1] > 230 and mid[2] > 220) 
            
            has_bottom_white_bar = (bot[0] > 225 and bot[1] > 225 and bot[2] > 215)
            has_top_white_bar = (top[0] > 220 and top[1] > 220 and top[2] > 210)

            state_desc = []
            if is_black_screen: state_desc.append("🌑 冷啟動黑屏")
            elif is_splash_aurora: state_desc.append("🌅 開屏夕陽極光")
            elif is_night_base: state_desc.append("🌌 開屏夜幕色")
            elif is_white_paper_app: state_desc.append("📄 主畫面和紙色")
            
            if has_bottom_white_bar: state_desc.append("⚠️ 底部米白條(#F6F5EE)")
            if has_top_white_bar: state_desc.append("⚠️ 頂部米白條")

            summary_str = f"[{current_time:05.2f}s] Top: RGB{top} | Mid: RGB{mid} | Bot: RGB{bot} | {' / '.join(state_desc) if state_desc else '過渡中'}"
            print(summary_str)
            analysis_log.append({
                "time": current_time,
                "top": top,
                "mid": mid,
                "bot": bot,
                "summary": " / ".join(state_desc)
            })

            # 保存關鍵切換點幀圖片
            if frame_idx % 4 == 0 or "⚠️" in "".join(state_desc) or "🌅" in "".join(state_desc):
                data = frame_data["dataUrl"].split(",")[1]
                img_path = OUTPUT_DIR / f"{prefix}_frame_{current_time:05.2f}s.jpg"
                with open(img_path, "wb") as f:
                    f.write(base64.b64decode(data))

            current_time = round(current_time + sample_interval, 2)
            frame_idx += 1

        browser.close()
        return {
            "meta": {"width": width, "height": height, "duration": duration},
            "frames": analysis_log
        }

if __name__ == "__main__":
    phone_res = analyze_video("ScreenRecording_10-10-2026 21-54-11_1.MP4", "phone", sample_interval=0.25)
    tablet_res = analyze_video("ScreenRecording_10-10-2026 21-55-40_1.MP4", "tablet", sample_interval=0.25)

    report_path = Path("docs/research/video_frame_telemetry.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"phone": phone_res, "tablet": tablet_res}, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 逐幀遙測分析完成！報告已儲存至: {report_path}")
    server.shutdown()
