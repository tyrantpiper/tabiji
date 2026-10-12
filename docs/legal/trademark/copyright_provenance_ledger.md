# Tabiji 原創美術著作創作履歷與數位存證清冊 (Copyright Provenance Ledger)

> **著作權人**: Ryan Su (創辦人兼原始著作權人)  
> **保護條款**: All Rights Reserved（保留所有權利，詳見 `frontend/public/LICENSE-ASSETS.md`）  
> **創作歷程與原創對話錨點**: Conversation ID `bb0db1c7-bfcd-4310-ad2a-c65daf5a1fdd`（Tabiji Branding And Trademark Analysis）  
> **加密技術存證**: SHA-256 雜湊值指紋  

---

## 一、 數位資產 SHA-256 密碼學指紋存證 (Cryptographic Fingerprints)

以下為本專案正式生產環境與商標送件素材之不可篡改雜湊清單（可用於國內外著作權訴訟或侵權舉證）：

| 資產名稱 | 實體檔案路徑 | 尺寸 / 像素 | 檔案大小 (Bytes) | SHA-256 雜湊指紋 |
| :--- | :--- | :--- | :--- | :--- |
| **首頁圖騰：揹包旅人立繪** | `frontend/public/images/tabiji-person-outline.png` | 1630 × 2546 | 244,602 | `87221aa283a5f9861bbd9cf38d1f5d27a1dff49616749efbd52a4f342bf045d6` |
| **開屏原畫：手繪長袍原圖** | `frontend/public/images/tabiji-art-mask.png` | 2048 × 2048 | 109,489 | `4294a7295409dc8a48febcdf220a5ab9f2985679b78d3ac2411ff46c229f0309` |
| **手寫草寫體：tabiji 字標** | `frontend/public/images/tabiji-cursive-logo.png` | 向量墨線遮罩 | 34,472 | `0eda6459dee0e4592318eb137bb30344600ec2255f711de383f53aaf1bbdd446` |
| **開屏獨立微層：3D紙飛機** | `frontend/public/images/tabiji-paper-plane.png` | 133 × 131 | 2,813 | `3b297db40a722077a66a998b3587622311a6182e39f5da0744a9c7a3c0eb6e36` |
| **日落極光底圖** | `frontend/public/images/tabiji-aurora-bg.png` | 1024 × 1024 | 61,667 | `f1419aa4a821310a173e4d9fed66c73c009e8bdca359babd8243960c3aee04c6` |
| **App 主圖示 (512x512)** | `frontend/public/icon.png` | 512 × 512 | 190,384 | `10a2514f39068845819056677518b89ecdf6b0ab87563e475482e0edc3ceb5b1` |
| **App 行動端圖示 (192x192)** | `frontend/public/icon-192.png` | 192 × 192 | 31,034 | `1dfeb50e7169ffef0c32aab9aba41b33d55a5306fa7314c0346dccb2f439781b` |

---

## 二、 動態商標 6 幀時序圖樣 SHA-256 存證

| 影格 | 實體檔案路徑 | 檔案大小 (Bytes) | SHA-256 雜湊指紋 |
| :--- | :--- | :--- | :--- |
| **Frame 1** | `docs/legal/trademark/motion/frame_01.png` | 4,290 | `af4c47be56d9dca19129b2a0b310dacb4491a2c5c107365ffe559240cfc76095` |
| **Frame 2** | `docs/legal/trademark/motion/frame_02.png` | 57,945 | `07d36a751fe0999a31f45455ff4092afdd8943dde26f1d848be90785dfbc7e03` |
| **Frame 3** | `docs/legal/trademark/motion/frame_03.png` | 121,779 | `09775672b792bcf31dede6d5da32cf8de442c546c9aa7e63fd88c17e7d97e8c2` |
| **Frame 4** | `docs/legal/trademark/motion/frame_04.png` | 196,565 | `686ba2680ca957ff65bb0c592f16919a41453400c621f43f8ff54a86641c1398` |
| **Frame 5** | `docs/legal/trademark/motion/frame_05.png` | 172,053 | `632f89e87b1b7db7a34c7fc2799dbd5455658a06c0b585493fef37bab481eef3` |
| **Frame 6** | `docs/legal/trademark/motion/frame_06.png` | 138,487 | `9870e10a878aa61a8d2ffbe7c73d6e62c802fd5ab6cda4f10ffab597f0a5e474` |

---

## 三、 著作權原創演進與歷史對話溯源 (Chronological Provenance)

1. **創作起點與命名（2026 年 10 月 8 日）**：
   - 買下 `tabijiapp.com` 網域，確立品牌由 `Tabidachi` 邁向 `Tabiji`。
2. **開屏原畫提供與解耦（2026 年 10 月 8 日 ~ 9 日）**：
   - 用戶於桌面提供 `animation.jpeg`（一筆劃藤井風長袍人物連寫 tabiji 與紙飛機），經沙盒圖像解耦分離出 `tabiji-art-mask.png` 與 `tabiji-paper-plane.png`。
3. **三幕式動態漸層渲染確立（2026 年 10 月 9 日）**：
   - 用戶提出夜幕起點 (0.0s) ➔ 風與光軌甦醒 (0.5s) ➔ 日落旅路 (1.2s~2.0s) 之三幕漸層與水墨暈開動態意象，固化於 `tabiji-splash-animation.tsx`。
4. **核心品牌立繪升級為「背包旅人」（2026 年 10 月 10 日）**：
   - 用戶提供 `D:\User\桌面\backpack.jpeg`，確立以背負掀蓋皮帶釦旅行後背包、回眸深情的人物墨線立繪（1630 × 2546）作為 Tabiji 核心 Brand Icon，取代舊版單一風衣人物，並實裝於 `landing-page.tsx`。
5. **程式碼轉授權與資產所有權保留（2026 年 10 月 10 日）**：
   - 建立 Git Tag `v1.0.0-mit-final` 劃界；程式碼升級為 PolyForm Noncommercial 1.0.0，全域視覺資產宣告 All Rights Reserved。
