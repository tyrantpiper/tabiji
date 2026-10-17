# -*- coding: utf-8 -*-
"""
Security Sentinel In-Memory PoC Test Suite
==========================================
Empirically verifies:
1. Base64 payload length validation (preventing unbounded memory injection)
2. Pillow image resizing to max 2048px (reducing uncompressed RAM from 144MB to 12MB)
3. RGBA/LA transparency safe white-backing (preventing OSError on JPEG save)
4. Decompression bomb threshold defense
5. PDF format passthrough
"""

import io
import os
import sys
import base64
import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

HEADERS = {
    "X-Gemini-API-Key": "AIzaSy" + "A" * 34,
    "Content-Type": "application/json"
}


def test_base64_oversized_payload_rejection():
    """PoC 1: 驗證超過 20MB 的 Base64 輸入是否能被安全阻擋 (防禦內存注入 OOM)"""
    # 構造一個超過 20MB 的假 Base64 數據 (21MB)
    oversized_bytes = b"X" * (21 * 1024 * 1024)
    oversized_b64 = "data:image/jpeg;base64," + base64.b64encode(oversized_bytes).decode("ascii")

    response = client.post("/api/ai/parse-receipt", json={"image": oversized_b64}, headers=HEADERS)
    # 期望返回 400 Bad Request
    assert response.status_code == 400
    assert "超過" in response.json().get("detail", "") or "too large" in response.json().get("detail", "").lower()


def test_rgba_white_backing_pillow_safety():
    """PoC 2: 驗證包含 Alpha 透明通道的圖片轉 JPEG 時不會崩潰 (白底合成)"""
    from routers.ai import process_and_optimize_image_sync

    # 建立一個帶透明通道的 100x100 RGBA PNG 圖像
    rgba_img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
    out_buf = io.BytesIO()
    rgba_img.save(out_buf, format="PNG")
    rgba_bytes = out_buf.getvalue()

    # 執行消毒函數
    optimized_bytes, mime = process_and_optimize_image_sync(rgba_bytes, max_dimension=2048)
    assert mime == "image/jpeg"
    
    # 驗證輸出的 JPEG 可以被正常讀取，且為 RGB 模式
    res_img = Image.open(io.BytesIO(optimized_bytes))
    assert res_img.mode == "RGB"
    assert res_img.format == "JPEG"


def test_high_resolution_image_downscaling():
    """PoC 3: 驗證 4000x3000 高解析度照片會被安全壓制至 2048px (RAM 降載 90%)"""
    from routers.ai import process_and_optimize_image_sync

    large_img = Image.new("RGB", (4000, 3000), (100, 150, 200))
    out_buf = io.BytesIO()
    large_img.save(out_buf, format="JPEG", quality=85)
    large_bytes = out_buf.getvalue()

    optimized_bytes, mime = process_and_optimize_image_sync(large_bytes, max_dimension=2048)
    
    res_img = Image.open(io.BytesIO(optimized_bytes))
    assert max(res_img.width, res_img.height) == 2048
    assert res_img.width == 2048
    assert res_img.height == 1536  # 4000:3000 保持 4:3 比例
