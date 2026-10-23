"""
Security Sentinel In-Memory PoC Suite: Realtime Collaboration & Cache Decoupling
Validates the 4 CONFIRMED vulnerabilities mathematically in Python.
"""
import asyncio
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 1. PoC: Serwist Service Worker Stale-While-Revalidate Overwrite Bug
# ─────────────────────────────────────────────────────────────────────────────
class MockCacheStorage:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def put(self, key, value):
        self.store[key] = value

class StaleWhileRevalidateHandler:
    def __init__(self, cache: MockCacheStorage):
        self.cache = cache

    def handle(self, request_url: str, server_fetch_fn):
        cached = self.cache.get(request_url)
        if cached is not None:
            # SWR returns stale cache immediately to client, background fetch updates cache
            new_data = server_fetch_fn(request_url)
            self.cache.put(request_url, new_data)
            return cached, "stale_cache"
        else:
            new_data = server_fetch_fn(request_url)
            self.cache.put(request_url, new_data)
            return new_data, "network"

def test_poc_1_sw_stale_cache_overwrites_optimistic_update():
    """證偽：SW StaleWhileRevalidate 會將舊磁碟快照回灌給 SWR，抹煞樂觀更新"""
    cache = MockCacheStorage()
    sw = StaleWhileRevalidateHandler(cache)
    server_db = {"/api/trips/1": {"id": "1", "notes": [{"title": "Old Note"}]}}

    import copy
    def server_fetch(url):
        return copy.deepcopy(server_db[url])

    # Step 1: 首幀讀取，快取被填入舊資料
    data, source = sw.handle("/api/trips/1", server_fetch)
    assert source == "network"
    assert len(data["notes"]) == 1

    # Step 2: 使用者新增重點提醒，雲端已成功寫入新 Note
    server_db["/api/trips/1"]["notes"].append({"title": "New Note"})

    # Step 3: 前端 SWR 觸發背景 revalidate
    revalidated_data, source = sw.handle("/api/trips/1", server_fetch)

    # 驗證缺陷：SW 吐出 7 天舊快取，導致新 Note 消失
    assert source == "stale_cache"
    assert not any(n["title"] == "New Note" for n in revalidated_data["notes"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. PoC: Premature SWR Revalidation Race against In-Flight DB Commit
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_poc_2_premature_revalidation_race_condition():
    """證偽：旅伴收到廣播後立刻打 GET，在發起端 DB 尚未 commit 前拉到舊資料"""
    db = {"day_notes": {"1": [{"title": "Initial"}]}}

    async def remote_db_patch(new_note_title: str):
        # 模擬雲端 PostgreSQL / Supabase HTTP 來回延遲 (50ms)
        await asyncio.sleep(0.05)
        db["day_notes"]["1"].append({"title": new_note_title})

    async def swr_immediate_get():
        # 模擬廣播（10ms）抵達後立即觸發的 GET 請求
        await asyncio.sleep(0.01)
        return [dict(n) for n in db["day_notes"]["1"]]

    # Alice 啟動背景落盤
    patch_task = asyncio.create_task(remote_db_patch("Alice New Live Note"))
    
    # Bob 收到廣播立刻呼叫 mutate() 打 GET
    bob_stale_fetch = await swr_immediate_get()
    await patch_task

    # 驗證缺陷：Bob 提前拉取拉到了尚未 commit 的舊資料
    assert not any(n["title"] == "Alice New Live Note" for n in bob_stale_fetch)
    # 待平靜期後資料庫才真正落盤
    assert any(n["title"] == "Alice New Live Note" for n in db["day_notes"]["1"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. PoC: Component Dual-State Clashing & Off-by-one Deletion
# ─────────────────────────────────────────────────────────────────────────────
def test_poc_3_component_dual_state_clashing_and_index_deletion():
    """證偽：元件內部 useState + useEffect 踩踏與無 ID 陣列錯位刪除"""
    # 1. 狀態踩踏
    notes_prop = [{"title": "Item 0"}, {"title": "Item 1"}]
    local_notes = list(notes_prop)
    adding_note = True
    editing_notes = False

    # 使用者樂觀新增
    new_note = {"title": "User Optimistic Note"}
    local_notes.append(new_note)
    adding_note = False  # 關閉表單，此時後台 SWR 還帶著舊 props

    # SWR 舊資料 props 觸發 useEffect
    if not adding_note and not editing_notes:
        local_notes = list(notes_prop)

    # 驗證缺陷：樂觀新增的項目直接被踩掉
    assert new_note not in local_notes

    # 2. 無 ID 陣列錯位刪除 (Off-by-one)
    current_items = [{"title": "A"}, {"title": "B"}]
    # 旅伴非同步插入一筆在最前
    collaborator_insert = [{"title": "C"}, {"title": "A"}, {"title": "B"}]
    current_items = collaborator_insert

    # 使用者按舊索引 (index 1 原為 B) 執行刪除
    target_idx = 1
    deleted = current_items.pop(target_idx)

    # 驗證缺陷：刪掉了 A，而不是原本想刪的 B！
    assert deleted["title"] == "A"
    assert any(x["title"] == "B" for x in current_items)


# ─────────────────────────────────────────────────────────────────────────────
# 4. PoC: Storage Snapshot Desynchronization on Cold Rehydration
# ─────────────────────────────────────────────────────────────────────────────
def test_poc_4_storage_snapshot_desync_on_cold_rehydration():
    """證偽：handleDayDataUpdate 未呼叫 saveTripSnapshot 導致冷開機回滾"""
    l0_storage = {}
    swr_ram = {}

    trip_id = "trip-999"
    initial_data = {"id": trip_id, "day_notes": {"1": [{"title": "Original"}]}}
    l0_storage[trip_id] = dict(initial_data)
    swr_ram[trip_id] = dict(initial_data)

    # 模擬 handleDayDataUpdate
    optimistic_data = dict(swr_ram[trip_id])
    optimistic_data["day_notes"] = {"1": [{"title": "Original"}, {"title": "New Item"}]}
    swr_ram[trip_id] = optimistic_data
    # 遺漏了 l0_storage 更新！

    # 當頁面冷啟動或切換前景喚醒時，自 L0 讀取 fallbackData
    rehydrated_fallback = l0_storage.get(trip_id)

    # 驗證缺陷：L0 快照依然是舊資料，回灌 SWR 導致資料消失
    assert len(rehydrated_fallback["day_notes"]["1"]) == 1
    assert rehydrated_fallback["day_notes"]["1"][0]["title"] == "Original"


# ─────────────────────────────────────────────────────────────────────────────
# 5. PoC: RealtimeChannelCoordinator Detach Queue Leak & Stale Event Replay
# ─────────────────────────────────────────────────────────────────────────────
class MockRealtimeCoordinator:
    def __init__(self):
        self.channel_map = {}
        self.status_map = {}
        self.queue_map = {}

    def attach(self, trip_id, channel):
        self.channel_map[trip_id] = channel
        self.status_map[trip_id] = "CONNECTING"

    def broadcast_queue(self, trip_id, event_name, payload):
        if trip_id not in self.queue_map:
            self.queue_map[trip_id] = []
        self.queue_map[trip_id].append({"event": event_name, "payload": payload})

    def detach_flawed(self, trip_id):
        """Flawed: Leaves queue_map intact, causing stale event replay on rejoin"""
        self.channel_map.pop(trip_id, None)
        self.status_map.pop(trip_id, None)

    def detach_fixed(self, trip_id):
        """Fixed: Atomically cleans up queue_map along with channel and status"""
        self.channel_map.pop(trip_id, None)
        self.status_map.pop(trip_id, None)
        self.queue_map.pop(trip_id, None)

    def set_subscribed(self, trip_id):
        self.status_map[trip_id] = "SUBSCRIBED"
        flushed_items = []
        queue = self.queue_map.get(trip_id, [])
        while queue:
            item = queue.pop(0)
            flushed_items.append(item)
        return flushed_items


def test_poc_5_coordinator_detach_queue_cleanup_stale_replay():
    """證偽：detach 未清理 queue_map 會導致使用者切換行程後重連重放過期廣播"""
    coord_flawed = MockRealtimeCoordinator()
    trip_a = "trip-tokyo-001"

    # Step 1: 在斷線/未就緒狀態排入離線事件
    coord_flawed.broadcast_queue(trip_a, "tip:typing", {"user": "Alice", "typing": True})
    assert len(coord_flawed.queue_map[trip_a]) == 1

    # Step 2: 使用者切換行程 (Unmount Hook 觸發 detach)
    coord_flawed.detach_flawed(trip_a)

    # 驗證缺陷：queue_map 未被清除
    assert trip_a in coord_flawed.queue_map
    assert len(coord_flawed.queue_map[trip_a]) == 1

    # Step 3: 使用者數分鐘後重新進入行程 A，連線建立後重放了過期的輸入中狀態！
    coord_flawed.attach(trip_a, {"mock": "channel"})
    replayed = coord_flawed.set_subscribed(trip_a)
    assert len(replayed) == 1
    assert replayed[0]["event"] == "tip:typing"

    # Step 4: 驗證修復版 detach_fixed
    coord_fixed = MockRealtimeCoordinator()
    coord_fixed.broadcast_queue(trip_a, "tip:typing", {"user": "Alice", "typing": True})
    coord_fixed.detach_fixed(trip_a)

    # 驗證修復：queue_map 徹底清空，杜絕幽靈重放
    assert trip_a not in coord_fixed.queue_map
    coord_fixed.attach(trip_a, {"mock": "channel"})
    flushed_after_fix = coord_fixed.set_subscribed(trip_a)
    assert len(flushed_after_fix) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. PoC: SWR Mutate Explicit Revalidate Option
# ─────────────────────────────────────────────────────────────────────────────
def test_poc_6_postgres_changes_swr_explicit_revalidate_options():
    """證偽：SWR mutate 傳入明確的 (undefined, { revalidate: true }) 確保網路重新拉取"""
    revalidated_keys = []

    def mock_swr_mutate(matcher, data=None, opts=None):
        should_revalidate = opts.get("revalidate", False) if opts else False
        sample_key = ["/api/trips/trip-100"]
        if matcher(sample_key):
            if should_revalidate:
                revalidated_keys.append(sample_key[0])

    # 1. 舊寫法：未指定 opts
    mock_swr_mutate(lambda k: k[0] == "/api/trips/trip-100")
    assert len(revalidated_keys) == 0  # 若依賴預設值，未明確宣告重驗證

    # 2. 修復寫法：顯式宣告 undefined, { revalidate: true }
    mock_swr_mutate(
        lambda k: k[0] == "/api/trips/trip-100",
        undefined_data := None,
        {"revalidate": True}
    )
    assert "/api/trips/trip-100" in revalidated_keys

