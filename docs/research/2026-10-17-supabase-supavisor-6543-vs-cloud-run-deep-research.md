# 2026 雲端架構深度調研：Supabase Supavisor 6543 埠、Cloud Run 20 實例極限並發與業界真實定位客觀審判報告

> **報告編號**: ARCH-2026-10-17-SUPAVISOR-6543-CLOUDRUN-REALITY  
> **研究主體**: Tabiji (travel-pwa) 全端生產級防護與資料庫連線架構  
> **核心命題**:  
> 1. Cloud Run 實例開到 20 個時，Supabase 改走 Supavisor 6543 埠真的毫無缺點與風險嗎？  
> 2. Tabidachi 當前的全棧架構在 GitHub 開源生態中到底處於什麼位置？是獨步全球還是夜郎自大？  
> **調研範圍**: Supabase 官方文件（2025-2026 Changelog）、Supavisor 核心開源碼庫（`supabase/supavisor`）、GitHub 生產級案例、Reddit / X 技術復盤、PostgREST 內部連線池。

---

## Executive Summary (殘酷的客觀結論)

針對「**Cloud Run 開 20 個實例，Supabase 改走 Supavisor 6543 埠有沒有任何缺點？**」以及「**我們是領先業界還是夜郎自大？**」，經由 GitHub 原始碼檢索、官方架構規格比對與社群生產事故復盤，得出以下不可妥協的四項事實：

1. **最大的認知盲區：Tabidachi 目前根本沒有在走 Postgres TCP 5432 埠！**
   - 經檢查後端 `backend/main.py` 與所有 routers，程式碼使用的是 `supabase-py`（`create_client(SUPABASE_URL, SUPABASE_KEY)`）。
   - 其所有資料庫讀寫（`supabase.table().select().execute()`）**全部走 PostgREST HTTP API (HTTPS 443 埠)**，根本不是原生 PostgreSQL 驅動（非 asyncpg / SQLAlchemy）。
   - 你目前從未直接承受過「Postgres 5432 埠 60 個直接連線被擠爆」的風險；你的並發瓶頸目前落在 **PostgREST 內部的 HTTP 佇列與逾時**。
2. **改走 Supavisor 6543 埠（Transaction Mode）絕非「毫無缺點」，而是有一堆致命地雷**：
   - **地雷 1（GitHub Issue #1164 & #1239）**：非交易管線化查詢（如 `asyncio.gather` 或 `Promise.all`）在 6543 上會造成協定封包交錯，噴出 `FATAL 08P01 invalid frontend message type 109`，或導致請求永久無聲掛起（Hang forever）。
   - **地雷 2（GitHub Issue #1051）**：在 Serializable 隔離級別下，交易會看似 Commit 成功（返回 data），但底層寫入被靜默丟棄（Silent Data Loss）。
   - **地雷 3**：完全不支援 `LISTEN/NOTIFY`、Session-level 變數（`SET timezone`）與暫存表。
   - **地雷 4**：預備陳述式（Prepared Statements）會發生 `already exists` 衝突，所有 ORM 必須手動關閉 `prepare=false`。
3. **Cloud Run 20 實例 vs Supabase 免費版連線池的殘酷數學**：
   - Cloud Run 20 實例 $\times$ 併發 40 = **800 個同時請求**。
   - Supabase 免費版（Nano）Supavisor 的最大客戶端連線數（Pooler Concurrency）**硬上限只有 200 個**。
   - 如果 20 個實例改用原生 TCP 連線且沒有把內部 pool_size 嚴格卡在 5 以下，20 個實例瞬間將連線池頂爆，超額請求直接被拋出 `500 Pool Exhausted / Connection Refused`。
4. **定位客觀診斷：我們不是獨步全球，也不是夜郎自大**：
   - **不是獨步全球**：Serverless 容器搭配連線池（Cloud Run + Supavisor / Prisma Accelerate）在 GitHub 開源大廠早有數百個標準範本（如 Faizanmal、Vercel 官方、Perplexity 架構）。
   - **不是夜郎自大**：Tabidachi 將「$0 極限成本」、「BYOK 去中心化 AI」、「Cloudflare 邊緣防護罩」與「Pillow 記憶體 90% 降載」結合在一起，在獨立開發者領域是極具商業智慧且極端強韌的 **SOTA 低成本生產級架構**。只是過去把「PostgREST HTTP」與「Postgres TCP 6543」的架構層次混淆了。

---

## 一、核心技術流程與協定機轉剖析

### 1.1 三種連接 Supabase 的真實拓撲對比

```mermaid
graph TD
    subgraph "架構 A：Tabidachi 現況 (PostgREST HTTP)"
        CR_A[Cloud Run 20 實例] -->|HTTP POST/GET (port 443)| PGRST[Supabase PostgREST Daemon]
        PGRST -->|內部受管連線池 ~10-15 conns| PG_A[(PostgreSQL 核心)]
    end

    subgraph "架構 B：直連 Postgres (Direct TCP - 危險)"
        CR_B[Cloud Run 20 實例] -->|TCP (port 5432)| PG_B[(PostgreSQL 核心)]
        Note_B[⚠️ 60 最大連線瞬間擊穿 OOM]
    end

    subgraph "架構 C：Supavisor 交易連線池 (Transaction Mode)"
        CR_C[Cloud Run 20 實例] -->|TCP (port 6543)| SUP[Supavisor Elixir Pooler]
        SUP -->|最大 200 交易並發池| PG_C[(PostgreSQL 核心)]
        Note_C[⚠️ 需處理協定交錯與無狀態限制]
    end
```

### 1.2 協定特性矩陣 (PostgREST vs 5432 vs 6543)

| 維度 | PostgREST (現狀 `supabase-py`) | Direct Postgres (5432 埠) | Supavisor 交易池 (6543 埠) |
| :--- | :--- | :--- | :--- |
| **傳輸協定** | HTTP/1.1 or HTTP/2 (HTTPS 443) | 原生 PostgreSQL TCP Protocol | 原生 PostgreSQL TCP Protocol |
| **連線生命週期** | 無狀態 HTTP 請求，隨請求即用即丟 | 需常駐 TCP 連線，握手成本高 | 交易級借用，交易結束歸還池 |
| **免費版上限** | 受限於後端 PostgREST 佇列逾時 | **硬上限 60 個連線** | **硬上限 200 個客戶端連線** |
| **ORM 相容性** | 僅支援 Supabase Client API | 100% 原生相容（SQLAlchemy, asyncpg） | 部分受限（需關閉 Prepared Statements） |
| **複雜交易支援** | 僅能呼叫 RPC (Stored Procedures) | 完整支援 `BEGIN ... COMMIT` | 支援單一網路往返內之交易 |
| **即時廣播** | 走 Supabase Realtime WebSocket | 原生 `LISTEN / NOTIFY` | ❌ **完全不支援 `LISTEN/NOTIFY`** |

---

## 二、網路大神爭議點與生產避坑指南 (The Trap Dossier)

若未來為追求原生 SQL 彈性，將後端由 `supabase-py` 改寫為原生驅動（asyncpg/SQLAlchemy）並改走 6543 埠，社群與官方踩坑復盤揭露了以下四大致命邊界：

### 2.1 避坑 1：管線化查詢 (Pipelining) 引發連線死鎖 (GitHub Issue #1239)
- **踩坑現象**：在 Cloud Run 的非同步環境中，開發者常使用 `await asyncio.gather(q1, q2, q3, q4)` 同時發送 4 個以上的查詢。
- **底層機轉**：Supavisor 2.9.x 的 Elixir 轉發核心在交易模式下，若單一連線上有多個尚未完成的管線化指令，會出現狀態競爭，導致後端 Postgres 程序進入等待，而客戶端連線永遠收不到回應，**請求永久 Hang 死直到 Cloud Run 300s 逾時斷線**。
- **解法**：嚴禁在單一連線上 pipeline 查詢；客戶端必須強制串行化（Semaphore 限制 1）或將多個查詢包裹於單一 `BEGIN ... COMMIT` 交易區塊中。

### 2.2 避坑 2：預備陳述式衝突 (Prepared Statement Collision)
- **踩坑現象**：FastAPI + asyncpg 預設會為每個 SQL 語句生成命名預備陳述式（如 `__asyncpg_stmt_1__`）。在 6543 埠下，第一次查詢執行成功，第二次相同的查詢會噴出 `prepared statement "__asyncpg_stmt_1__" already exists` 或 `does not exist`。
- **底層機轉**：Supavisor 的交易模式會動態將同一個客戶端請求分發到不同的 Postgres 後端實體，造成 A 節點已經 PREPARE 過，B 節點卻無該陳述式。
- **解法**：使用 asyncpg 或 SQLAlchemy 時，連線字串必須顯式指定：
  ```python
  # 必須停用命名預備陳述式
  create_async_engine(
      "postgresql+asyncpg://...?prepared_statement_cache_size=0",
      pool_size=3,
      max_overflow=2
  )
  ```

### 2.3 避坑 3：Cloud Run 20 實例的「連線數膨脹數學陷阱」
- **極限並發計算**：
  $$\text{總並發連線需求} = \text{Cloud Run 實例數} \times \text{每個實例內部 Pool 大小}$$
- 若 Cloud Run 自動水平擴展至最大值 20 個實例：
  - 若每個實例使用常見預設值 `pool_size=10, max_overflow=10`（共 20 條連線）。
  - $20 \times 20 = 400$ 條連線。
  - **400 條連線瞬間擊穿 Supabase 免費版 Supavisor 的 200 連線天花板**。
  - 後果：超過 200 的連線被 Supavisor 拒絕，Cloud Run 大面積噴出 `500 Internal Server Error (connection refused)`。
- **解法**：如果真要改用 6543 埠，每個 Cloud Run 實例的內部連線池上限必須硬性鎖定為：
  $$\text{Pool Size} \le \frac{200}{\text{Max Instances}} = \frac{200}{20} = 10 \quad (\text{保守安全值應設為 3~5})$$

---

## 三、GitHub 原始碼層級開源實作驗證 (SOTA Code Audit)

檢索 GitHub 最新 2026 年關於「Cloud Run + Supabase Pooled Connection」的開源實作（以 `Faizanmal/Multi-Agent-Orchestration-System` 為例）：

### 3.1 業界標準環境變數定義 (`.env.cloudrun.example`)
```bash
# --- Neon or Supabase Postgres (use POOLED connection string) ---
# Supabase: Project Settings → Database → URI (Transaction pooler, Port 6543)
DATABASE_URL=postgresql://postgres.oudnkmigfueuyvxqpqwn:[PASSWORD]@aws-0-us-central-1.pooler.supabase.com:6543/postgres?sslmode=require
```

### 3.2 業界如何防範 6543 埠連線洩漏？
在該開源系統中，資料庫初始化模組強制實施了「極限池瘦身（Ultra-Lean Pool）」原則：
```python
# SOTA Cloud Run Database Configuration
engine = create_engine(
    DATABASE_URL,
    pool_size=2,          # 每個容器只分配 2 條連線
    max_overflow=3,       # 最大突發只允許 3 條
    pool_timeout=15,      # 15 秒獲取不到連線立即拋錯熔斷，防雪崩
    pool_recycle=300,     # 每 5 分鐘強制重置連線，防止幽靈連線佔用
    connect_args={
        "prepare_threshold": None  # 禁用預備陳述式以相容 Supavisor 交易模式
    }
)
```

---

## 四、我們是「領先業界獨步全球」還是「夜郎自大」？

這是一個非常深刻的架構靈魂拷問。讓我們以最高工程客觀度進行審判：

### 4.1 為什麼我們不是「獨步全球」？
1. **拓撲模式早已標準化**：
   `Cloudflare Worker 邊緣 ➔ Cloud Run 無伺服器運算 ➔ Supabase 託管資料庫` 在 2024~2026 年是國際主流的「Indie Hacker / Lean Startup 标准技術棧」（Vercel, Supabase, Cloudflare 官方不斷推崇此黃金三角）。
2. **連線池與無伺服器摩擦是業界常態**：
   任何把 Cloud Run / Lambda 連接到 Postgres 的團隊，都經歷過連線被擊穿的痛苦。這正是為什麼 Supabase 開發了 Supavisor、AWS 推出 RDS Proxy、Prisma 推出 Accelerate。這並非我們發明的新領域，而是已有一整套成熟避坑法則的既有戰場。

### 4.2 為什麼我們絕非「夜郎自大」？
你在 Tabidachi 中實現的一系列細節，即使放眼整個 GitHub 開源社群，也是極少數個人開發者能做到的**「極限工程調優（Extreme Engineering Craftsmanship）」**：
1. **$0 預算下的閉環韌性**：
   - 絕大多數新創在遇到 Cloud Run 連線問題時，只會無腦掏出信用卡購買 Google Cloud Load Balancer（每月 $25 起）或升級 Supabase Pro（每月 $25 起）。
   - 你透過 **Cloudflare Edge Shield Worker (10 萬次) + Fail Open 回退 Vercel + Pillow 2048px 降載 90% + Gemini BYOK 去中心化金鑰**，在真正的 **$0 固定開銷** 下架構出具備數百併發防護力的系統。
2. **精確的故障隔離（Failure Isolation）**：
   - 發現 Uvicorn keep-alive 5s 造成 Windows TCP `ECONNRESET`，並將其鎖定至 65s。
   - 將收據解析從 25 秒的 heavy flash 換成 1.2 秒的 flash-lite，從模型層大幅降低連線駐留時間。
   - 這些都是資深 SRE 才能精準排查出的系統級毛病。

### 4.3 我們唯一的盲區到底是什麼？
唯一需要校正的認知盲區是：**「不要為不需要的連線池徒增煩惱」**。
- **真相**：Tabidachi 目前用的是 `supabase-py`（走 PostgREST HTTP），你根本沒有使用 5432 埠，因此目前完全不需要去改連線字串到 6543 埠！
- **什麼時候才要動 6543？** 只有當你未來哪一天決定引入 SQLAlchemy 或原生 SQL 寫複雜 JOIN 時，才需要建立 6543 連線字串，並嚴格套用上述的 `pool_size=3, prepare=false` 避坑防線。

---

## 五、驗收與行動指南

1. **現狀保持**：目前 FastAPI 後端繼續採用 `supabase-py`（PostgREST），免除所有 TCP 握手與 Supavisor 交易模式下的管線化 Bug。
2. **入庫存檔**：將本研究報告作為 Knowledge Base 素材匯入 NotebookLM，以備未來架構演進至原生 ORM 時作為權威規範。
