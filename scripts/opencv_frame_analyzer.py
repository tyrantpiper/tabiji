import cv2
import numpy as np
import os
import sys
import json
from pathlib import Path

# Fix Windows cp950 encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_DIR = Path("docs/screenshots/frame_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def analyze_video(video_path: str, tag: str):
    print(f"\n=======================================================")
    print(f"🎬 OpenCV 逐幀硬核分析: {video_path}")
    print(f"=======================================================")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ 無法開啟影片: {video_path}")
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0

    print(f"📊 影片參數: {width} x {height} | {fps:.2f} FPS | 總幀數: {total_frames} | 時長: {duration:.2f}s")

    frame_idx = 0
    key_events = []
    
    # 底部白條高度監測
    prev_state = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_idx / fps
        # frame 是 BGR 格式
        
        # 1. 採樣頂部狀態列區域 (Top 4%)
        top_h = max(30, int(height * 0.04))
        top_crop = frame[0:top_h, :]
        top_bgr = np.mean(top_crop, axis=(0, 1)) # B, G, R
        top_rgb = [round(top_bgr[2], 1), round(top_bgr[1], 1), round(top_bgr[0], 1)]

        # 2. 採樣底部區域 (Bottom 5%)
        bot_h = max(40, int(height * 0.05))
        bot_crop = frame[height - bot_h:height, :]
        bot_bgr = np.mean(bot_crop, axis=(0, 1))
        bot_rgb = [round(bot_bgr[2], 1), round(bot_bgr[1], 1), round(bot_bgr[0], 1)]

        # 3. 採樣中央區域 (Center 20%)
        cw = int(width * 0.2)
        ch = int(height * 0.2)
        cx = int((width - cw) / 2)
        cy = int((height - ch) / 2)
        center_crop = frame[cy:cy+ch, cx:cx+cw]
        center_bgr = np.mean(center_crop, axis=(0, 1))
        center_rgb = [round(center_bgr[2], 1), round(center_bgr[1], 1), round(center_bgr[0], 1)]

        # 4. 精確測量底部橫條高度 (從最底行向上掃描，直到顏色不再是米白/淺灰色)
        # 和紙米白 #F6F5EE: R~246, G~245, B~238
        # 判定標準: R > 230 and G > 225 and B > 215
        bottom_bar_pixel_height = 0
        for y_offset in range(min(150, height)):
            row_y = height - 1 - y_offset
            row_bgr = np.mean(frame[row_y, :], axis=0) # [B, G, R]
            r, g, b = row_bgr[2], row_bgr[1], row_bgr[0]
            if (r > 230 and g > 225 and b > 215) or (r > 240 and g > 240 and b > 240):
                bottom_bar_pixel_height += 1
            else:
                # 遇到非白底行
                break

        # 狀態特徵判定
        is_black = (top_rgb[0] < 30 and center_rgb[0] < 30 and bot_rgb[0] < 30)
        is_splash_night = (center_rgb[0] < 45 and center_rgb[1] > 30 and center_rgb[2] > 35) # #162832
        is_splash_sunset = (center_rgb[0] > 70 and center_rgb[1] > 35 and center_rgb[2] < 70) # 橙紅夕陽
        is_app_main = (center_rgb[0] > 220 and center_rgb[1] > 220 and center_rgb[2] > 210) # 主畫面和紙色

        current_state = "未知"
        if is_black:
            current_state = "冷啟動黑屏"
        elif is_splash_night or is_splash_sunset:
            current_state = "開場動畫播放中"
        elif is_app_main:
            current_state = "主畫面展示中"

        # 偵測重要狀態躍遷
        if current_state != prev_state or (bottom_bar_pixel_height > 15 and frame_idx % int(fps) == 0):
            event_info = {
                "frame": frame_idx,
                "time_sec": round(timestamp, 3),
                "state": current_state,
                "top_rgb": top_rgb,
                "bot_rgb": bot_rgb,
                "center_rgb": center_rgb,
                "bottom_deadzone_px": bottom_bar_pixel_height
            }
            key_events.append(event_info)
            print(f"[{timestamp:05.2f}s | Frame {frame_idx:04d}] 狀態: {current_state:<10} | 頂部: RGB{top_rgb} | 底部死區: {bottom_bar_pixel_height:2d}px")

            # 保存關鍵幀圖片
            out_img = OUTPUT_DIR / f"{tag}_f{frame_idx:04d}_{timestamp:05.2f}s.jpg"
            cv2.imwrite(str(out_img), frame)

            prev_state = current_state

        frame_idx += 1

    cap.release()
    return {
        "tag": tag,
        "width": width,
        "height": height,
        "fps": fps,
        "total_frames": total_frames,
        "duration": duration,
        "events": key_events
    }

if __name__ == "__main__":
    phone_res = analyze_video("D:/User/桌面/ScreenRecording_10-10-2026 21-54-11_1.MP4", "phone")
    tablet_res = analyze_video("D:/User/桌面/ScreenRecording_10-10-2026 21-55-40_1.MP4", "tablet")

    with open("docs/research/opencv_frame_telemetry.json", "w", encoding="utf-8") as f:
        json.dump({"phone": phone_res, "tablet": tablet_res}, f, indent=2, ensure_ascii=False)
    print("\n✅ OpenCV 逐幀硬核分析全部完成！報告已儲存至 docs/research/opencv_frame_telemetry.json")
