# 領域知識庫：離線架構與 PWA 快取 (offline_pwa)

> **所屬領域**: Service Worker (Serwist), IndexedDB (idb-keyval), Cache Storage, PWA Standalone

## 🏛️ 架構決策 (Decisions)
- **Service Worker 構建路徑絕對化**: 靜態資產掃描以模組目錄 import.meta.url 為錨點解析絕對路徑，確保建構確定性。
- **輕量化離線原則**: 立足於專案既有 serwist、idb-keyval 與 SWRConfig provider 模式，以最小增量完成離線閉環。
- **動脈與靜脈讀寫分流架構**: GET 查詢走 SWR 快取，突變請求走 BackgroundSync 離線重試，兩者物理隔離。
- **PWA 帶參冷啟動導航防線**: app-shell-navigation 宣告 matchOptions: { ignoreSearch: true } 且逾時緊縮至 2s，確保離線 100% 命中 App Shell。
- **行程上下文離線防自我抹殺雙守衛**: isDefinitelyOnline && !isError 雙重核驗，只有確實在線且無錯誤才允許清空行程。
- **SWR ES6 Proxy 防抖持久化**: 以 ES6 Proxy 攔截 SWR 成功寫入，1500ms 防抖自動序列化持久化至 IndexedDB tabidachi_swr_persisted_cache。
- **推播分頁喚醒與內部事件廣播**: 推播點擊使用 client.focus() 喚醒，並以 postMessage 內部廣播 TABIDACHI_PUSH_NAVIGATE 平滑切換。
- **外部圖片快取容量解鎖**: 上限擴充至 300 張 (~30MB)，Cloudflare Worker 反向代理注入 Access-Control-Allow-Origin: * 防止 Safari Opaque 填充爆炸。
- **Precache 動靜態資產解耦**: 嚴禁將 Next.js 動態 Chunks 放進 install Precache，動態資源 100% 交由 runtimeCaching CacheFirst 接管。
- **Service Worker 絕不回傳 Response.error()**: Navigation Fallback 提供內聯 Zero-JS 物理 HTML/CSS 骨架，根絕瀏覽器斷網小恐龍。
- **WebKit 註冊快取隔離**: 註冊顯式指定 { updateViaCache: 'none' }，切斷內部 HTTP 緩存干擾。
- **Service Worker Ready 硬逾時防護**: 封裝 getReadyServiceWorker(timeoutMs=5000) 搭配 Promise.race，防止未就緒時無限期死鎖。
- **冷啟動零閃爍夜幕協調防線**: manifest.json 與 themeColor 鎖定為 #162832，硬骨架透過 standalone 媒體查詢自適應，水合掛載時無縫交棒。

## 🛡️ 踩坑記錄 (Failed Paths)
- **FP-007 (開發模式 SW 污染)**: npm run dev 預設阻斷 Service Worker 註冊以保護 HMR。測試離線走 npm run build && npm start。
- **FP-008 (退出意圖優先於實體訂閱)**: 實體訂閱退訂引入 push_opt_out 標記，偵測到退訂標記即便瀏覽器底層回傳訂閱，前端強制視為已退訂。
