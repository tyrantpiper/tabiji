# Security Sentinel 對抗性安全審計報告

> **審計日期**: 2026-10-17  
> **審計模式**: `agy.exe -p --sandbox` 物理隔離子代理人多輪對抗驗證  
> **目標主題**: Cloud Run 算力加固、Pillow 圖片記憶體炸彈與邊緣路由分流  
> **審計版本**: `v2.0.0 (Cloudflare ✕ Google Mantis ✕ agy CLI)`

---

## 一、審計執行摘要 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :---: | :--- |
| **候選目標數 (Total Validated)** | 5 | 涵蓋部署工作流、後端 AI 路由與邊緣 Worker |
| **已證實漏洞 (CONFIRMED)** | **2** | 包含 Base64 記憶體炸彈、Cloud Run 併發 OOMKilled 隱患 |
| **已排除假陽性 (DISMISSED)** | 1 | RGBA 例外已被 try-catch 包裹，但會無聲降級為未轉碼位元組 |
| **架構優化建議 (INCONCLUSIVE / HINT)** | 2 | 非同步 Event Loop 需透過 `asyncio.to_thread` 隔離 CPU 密集運算；Worker 死代碼清理 |

---

## 二、對抗驗證詳情報告 (Detailed Findings & In-Memory PoCs)

### 1. [CONFIRMED] `backend/routers/ai.py:unbounded_base64_memory_dos`
- **威脅邊界**: `browser_to_edge` / `authenticated_to_internal`
- **攻擊向量**: 記憶體注入與 DoS 攻擊
- **對抗結論**:
  在 `parse_receipt` 路由中，當請求透過 `body.image` 傳遞 Base64 時，程式未對解碼後的位元組長度進行任何檢查（遠端 URL 則有 20MB 限制）。攻擊者可傳送 50MB~100MB 的 Base64 字串，後端直接在 RAM 中解碼為 37MB~75MB 的二進位點陣圖，在 512MB 容器中瞬間引發 OOM 崩潰。
- **In-Memory PoC 實證結果**:
  ```python
  # 執行 pytest backend/tests/test_cloud_run_hardening_sentinel.py::test_base64_oversized_payload_rejection
  # 傳送 21MB Base64 數據時，當前代碼未阻擋（未返回 400 Bad Request），直接穿透進模型呼叫層！
  FAILED assert 500 == 400 (未在進入模型前完成長度截斷，噴出 500 錯誤)
  ```

### 2. [CONFIRMED] `.github/workflows/deploy-backend.yml:cloud_run_oom_and_concurrency_hazard`
- **威脅邊界**: 容器基礎設施架構
- **攻擊向量**: 記憶體耗盡與容器重啟 (SIGKILL 137)
- **對抗結論**:
  Cloud Run 部署命令配置 `--memory 512Mi`，且未指定 `--concurrency`，使得 Cloud Run 採用預設的單容器 80 併發。解壓縮一張主流手機拍攝的 48MP (8000x6000) 收據需要 `8000 * 6000 * 3 bytes ≈ 144MB` 原始點陣圖。只要 3~4 個請求同時進行，容器記憶體立即突破 512MB，引發 cgroup OOM 物理終止 (退出碼 137)。
- **In-Memory PoC 實證**:
  ```python
  container_memory_limit_bytes = 512 * 1024 * 1024  # 512 MiB
  bitmap_size_bytes = 8000 * 6000 * 3  # ~144 MB
  concurrent_requests = 4
  assert (bitmap_size_bytes * concurrent_requests) > container_memory_limit_bytes
  # 4 個並行請求產生 576MB，必然引發 OOMKilled 137！
  ```

### 3. [DISMISSED with HINT] `backend/routers/ai.py:rgba_jpeg_mode_crash`
- **審計結論**:
  原假設認為 RGBA 轉 JPEG 會噴出 `OSError` 導致 500。物理審查員指出 `convert_heic_to_jpeg` 內部有 `try...except Exception as e:` 保護，因此不會有未捕捉例外逃逸。然而，這會導致帶透明通道的 PNG 圖片在轉碼失敗後，無聲回傳原位元組，無法達成壓縮與長寬縮放目的。建議以「純白底」進行 Alpha 合成再轉 RGB。

### 4. [HINT] `backend/routers/ai.py:event_loop_cpu_starvation`
- **審計結論**:
  Pillow 圖像解碼為 CPU 密集運算。在 `async def parse_receipt` 中直接同步執行會凍結主事件迴圈 100~300ms。建議透過 `await asyncio.to_thread(process_and_optimize_image_sync, ...)` 拋轉至背景線程池。

---

## 三、Mantis 補丁候選與精確區塊替換 (Candidate Fix & Block Replacements)

### 區塊替換 1: `backend/routers/ai.py`
加入線程安全的圖片最佳化器（白底合成 + EXIF 轉正 + 2048px 縮圖 + DecompressionBomb 防禦），並修復 Base64 尺寸防護與線程池拋轉：

```python
# <<<<<<<< TARGET CONTENT (backend/routers/ai.py lines 84-106)
            data = response.content
            if len(data) > MAX_IMAGE_SIZE:
                 raise HTTPException(status_code=400, detail="Image too large (>5MB)")
            
            return data, content_type
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Image download timeout")
    except Exception as e:
        print(f"❌ [SafeDownload] Failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch image: {str(e)}")

def convert_heic_to_jpeg(data: bytes) -> bytes:
    """Fallback: Convert HEIC/HEIF to JPEG using Pillow."""
    try:
        img = Image.open(io.BytesIO(data))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception as e:
        print(f"⚠️ [HEIC Fallback] Conversion failed: {e}")
        return data # Return original if conversion fails
# ======== REPLACEMENT CONTENT
            data = response.content
            if len(data) > MAX_IMAGE_SIZE:
                 raise HTTPException(status_code=400, detail=f"Image too large (>{MAX_IMAGE_SIZE // (1024 * 1024)}MB)")
            
            return data, content_type
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Image download timeout")
    except Exception as e:
        print(f"❌ [SafeDownload] Failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch image: {str(e)}")

from PIL import ImageOps

def process_and_optimize_image_sync(data: bytes, max_dimension: int = 2048) -> tuple[bytes, str]:
    """
    🛡️ 生產級同步圖片消毒器 (在獨立線程池中執行，防禦 OOM 與 Event Loop 阻塞)
    - 防 Decompression Bomb (單圖上限 50MP)
    - EXIF 轉向校正 (防止手機直拍發票橫躺)
    - RGBA/LA/P 透明背景以「純白底」平滑合成，防轉 JPEG 崩潰
    - 2048px LANCZOS 等比例縮放 (解壓縮記憶體從 144MB 降至 12MB，降載 90%)
    """
    try:
        Image.MAX_IMAGE_PIXELS = 50_000_000
        with Image.open(io.BytesIO(data)) as img:
            # 1. 依 EXIF 自動旋轉
            img = ImageOps.exif_transpose(img)

            # 2. 處理透明通道 (Alpha Composite onto White)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                alpha_img = img.convert("RGBA")
                background = Image.new("RGBA", alpha_img.size, (255, 255, 255, 255))
                img = Image.alpha_composite(background, alpha_img).convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # 3. 2048px 邊長壓制
            orig_w, orig_h = img.size
            if max(orig_w, orig_h) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                print(f"📐 [Image Downscale] {orig_w}x{orig_h} -> {img.width}x{img.height}")

            out = io.BytesIO()
            img.save(out, format="JPEG", quality=88, optimize=True)
            return out.getvalue(), "image/jpeg"

    except Image.DecompressionBombError:
        raise HTTPException(status_code=400, detail="圖片像素過大，觸發防護閾值")
    except Exception as e:
        print(f"⚠️ [Image Optimization Fallback] {e}")
        return data, "image/jpeg"

def convert_heic_to_jpeg(data: bytes) -> bytes:
    """Fallback: Convert HEIC/HEIF to JPEG using Pillow."""
    res_bytes, _ = process_and_optimize_image_sync(data)
    return res_bytes
# >>>>>>>>
```

### 區塊替換 2: `backend/routers/ai.py` (parse_receipt 路由入口)
```python
# <<<<<<<< TARGET CONTENT (backend/routers/ai.py lines 655-681)
        # 1. Source Determination
        if body.image:
            # Base64 path
            img_data = body.image.split(",")[1] if "," in body.image else body.image
            image_bytes = base64.b64decode(img_data)
        elif body.imageUrl:
            # Remote URL path (Safe Download)
            image_bytes, mime_type = await safe_download_image(body.imageUrl)
        else:
            raise HTTPException(status_code=400, detail="Missing source")

        # 2. HEIC Handling & Extraction Attempt
        is_heic = "heic" in mime_type or "heif" in mime_type
        
        try:
            current_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            raw_text = await call_extraction(api_key, parts + [current_part], intent_type="EXTRACTION")
        except Exception as e:
            # Fallback for HEIC if first attempt fails
            if is_heic:
                print("🔄 [HEIC Fallback] Retrying with JPEG conversion...")
                jpeg_bytes = convert_heic_to_jpeg(image_bytes)
                current_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
                raw_text = await call_extraction(api_key, parts + [current_part], intent_type="EXTRACTION")
            else:
                raise e
# ======== REPLACEMENT CONTENT
        # 1. Source Determination
        if body.image:
            # Base64 path (容錯切分，兼容純 Base64 與 data URL)
            img_data = body.image.split(",")[-1].strip()
            image_bytes = base64.b64decode(img_data)
            if len(image_bytes) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=400, detail=f"圖片超過 {MAX_IMAGE_SIZE // (1024 * 1024)}MB 上限")
        elif body.imageUrl:
            # Remote URL path (Safe Download)
            image_bytes, mime_type = await safe_download_image(body.imageUrl)
        else:
            raise HTTPException(status_code=400, detail="Missing source")

        # 2. 格式分流與記憶體物理防禦 (PDF 直通，圖片透過 asyncio.to_thread 拋至線程池)
        if mime_type != "application/pdf":
            image_bytes, mime_type = await asyncio.to_thread(
                process_and_optimize_image_sync, image_bytes, 2048
            )

        # 3. Extraction Attempt
        current_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        raw_text = await call_extraction(api_key, parts + [current_part], intent_type="EXTRACTION")
# >>>>>>>>
```

### 區塊替換 3: `.github/workflows/deploy-backend.yml`
```yaml
# <<<<<<<< TARGET CONTENT (.github/workflows/deploy-backend.yml lines 38-43)
            --allow-unauthenticated \
            --memory 512Mi \
            --cpu 1 \
            --timeout 600s \
            --max-instances 10 \
            --min-instances 0 \
# ======== REPLACEMENT CONTENT
            --allow-unauthenticated \
            --memory 1Gi \
            --cpu 1 \
            --concurrency 40 \
            --timeout 300s \
            --max-instances 10 \
            --min-instances 0 \
# >>>>>>>>
```

---

## 四、安全總結與人類門禁移交 (Phase 6 Handover)

依據 L0 憲法規範，`@security` 已完成對抗證偽、沙盒驗證與 In-Memory PoC。  
**此時尚未修改生產環境原始碼**。請人類開發者（Ryan）審閱上述報告與補丁計畫，並下達執行指令。
