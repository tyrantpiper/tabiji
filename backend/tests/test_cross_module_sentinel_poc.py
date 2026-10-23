"""
Security Sentinel In-Memory PoC Suite: Cross-Module Collaboration & L0 Snapshot Fidelity
Validates the cross-module real-time sync, SWR tuple key matching, React state closure escape, and L0 snapshot rollback mathematically in Python.
"""
import copy
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. PoC: SWR Tuple Key Predicate Matching vs Simple String Match
# ─────────────────────────────────────────────────────────────────────────────
class MockSWRGlobalCache:
    def __init__(self):
        self.cache = {}

    def set(self, key, value):
        # SWR keys can be string or tuple
        self.cache[key if isinstance(key, str) else tuple(key)] = value

    def mutate_exact_string(self, target_str_key, new_value):
        """Old flawed approach: expects exact match against a string"""
        count = 0
        for k in list(self.cache.keys()):
            if k == target_str_key:
                self.cache[k] = new_value
                count += 1
        return count

    def mutate_predicate(self, predicate_fn, new_value):
        """New Mantis patch: evaluates predicate supporting Tuple keys"""
        count = 0
        for k in list(self.cache.keys()):
            # SWR passes the raw key (list/tuple or string) to predicate
            key_repr = list(k) if isinstance(k, tuple) else k
            if predicate_fn(key_repr):
                self.cache[k] = new_value
                count += 1
        return count


def test_poc_1_swr_tuple_key_predicate_mismatch():
    """證偽：SWR 使用 Tuple 註冊費用快取時，字串比對完全失靈，必須使用 Predicate"""
    swr = MockSWRGlobalCache()
    trip_id = "trip-tokyo-2026"
    user_id = "user-ryan-888"

    # useExpenses registers SWR with tuple: [`/api/trips/${tripId}/expenses`, userId]
    tuple_key = (f"/api/trips/{trip_id}/expenses", user_id)
    swr.set(tuple_key, [{"id": "exp-1", "amount": 1200, "item": "Ramen"}])

    # 1. 舊邏輯/不嚴謹假定：字串比對 mutate("/api/trips/trip-tokyo-2026/expenses")
    updated_items = [{"id": "exp-1", "amount": 1200}, {"id": "exp-2", "amount": 3000}]
    matched = swr.mutate_exact_string(f"/api/trips/{trip_id}/expenses", updated_items)

    # 驗證缺陷：字串比對完全沒有命中任何 Tuple 快取！
    assert matched == 0
    assert len(swr.cache[tuple_key]) == 1  # 依然停留在舊資料

    # 2. Mantis 安全補丁：Tuple Predicate 比對
    def expense_predicate(key):
        if isinstance(key, list) and len(key) > 0 and isinstance(key[0], str):
            return key[0].startswith(f"/api/trips/{trip_id}/expenses")
        return False

    matched_predicate = swr.mutate_predicate(expense_predicate, updated_items)

    # 驗證修復：成功精確命中複合鍵並完成快取更新！
    assert matched_predicate == 1
    assert len(swr.cache[tuple_key]) == 2
    assert swr.cache[tuple_key][1]["id"] == "exp-2"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PoC: React State Closure Overwrite in handleSaveInner
# ─────────────────────────────────────────────────────────────────────────────
class MockInfoViewComponent:
    def __init__(self):
        self.state_hotels = [{"id": "hotel-1", "name": "Old Hotel A"}]
        self.backend_db = {"hotel_info": copy.deepcopy(self.state_hotels)}
        self.l0_snapshot = copy.deepcopy(self.state_hotels)

    def handle_save_flawed(self):
        """Flawed: closes over self.state_hotels without accepting override argument"""
        # Reads self.state_hotels from closure
        self.backend_db["hotel_info"] = copy.deepcopy(self.state_hotels)
        self.l0_snapshot = copy.deepcopy(self.state_hotels)

    def handle_save_fixed(self, override_hotels=None):
        """Fixed: accepts explicit override parameter escaping stale closure"""
        target = override_hotels if override_hotels is not None else self.state_hotels
        self.backend_db["hotel_info"] = copy.deepcopy(target)
        self.l0_snapshot = copy.deepcopy(target)

    def simulate_handle_save_inner_flawed(self, temp_hotel):
        new_hotels = copy.deepcopy(self.state_hotels)
        new_hotels[0] = temp_hotel
        # React state update is async/batched: self.state_hotels is NOT yet updated in current frame!
        # Calling handle_save_flawed immediately:
        self.handle_save_flawed()
        # Simulated next tick state flush:
        self.state_hotels = new_hotels

    def simulate_handle_save_inner_fixed(self, temp_hotel):
        new_hotels = copy.deepcopy(self.state_hotels)
        new_hotels[0] = temp_hotel
        # Fixed: passes new_hotels explicitly
        self.handle_save_fixed(override_hotels=new_hotels)
        self.state_hotels = new_hotels


def test_poc_2_info_view_stale_closure_overwrites_temp_hotel():
    """證偽：handleSave 若不支援覆寫參數，React 非同步更新導致向後端送出過期舊飯店資訊"""
    # 測試缺陷版本
    comp_flawed = MockInfoViewComponent()
    updated_hotel = {"id": "hotel-1", "name": "Imperial Hotel Tokyo (Updated)"}
    comp_flawed.simulate_handle_save_inner_flawed(updated_hotel)

    # 驗證缺陷：後端與 L0 快照收到的仍然是 Old Hotel A，使用者編輯遺失！
    assert comp_flawed.backend_db["hotel_info"][0]["name"] == "Old Hotel A"
    assert comp_flawed.l0_snapshot[0]["name"] == "Old Hotel A"

    # 測試修復版本
    comp_fixed = MockInfoViewComponent()
    comp_fixed.simulate_handle_save_inner_fixed(updated_hotel)

    # 驗證修復：成功克服 React 閉包延遲，後端與 L0 快照皆為最新更新！
    assert comp_fixed.backend_db["hotel_info"][0]["name"] == "Imperial Hotel Tokyo (Updated)"
    assert comp_fixed.l0_snapshot[0]["name"] == "Imperial Hotel Tokyo (Updated)"


# ─────────────────────────────────────────────────────────────────────────────
# 3. PoC: L0 Snapshot Rollback Protection on Network Failure
# ─────────────────────────────────────────────────────────────────────────────
class MockItineraryDataManager:
    def __init__(self, confirmed_trip):
        self.confirmed_trip = copy.deepcopy(confirmed_trip)
        self.swr_cache = copy.deepcopy(confirmed_trip)
        self.l0_snapshot = copy.deepcopy(confirmed_trip)

    def optimistic_update(self, optimistic_trip, persist_to_l0_immediately=True):
        self.swr_cache = copy.deepcopy(optimistic_trip)
        if persist_to_l0_immediately:
            self.l0_snapshot = copy.deepcopy(optimistic_trip)

    def handle_error_rollback_flawed(self):
        """Flawed: rolls back SWR cache, but forgets to restore L0 snapshot"""
        self.swr_cache = copy.deepcopy(self.confirmed_trip)
        # BUG: l0_snapshot is NOT reverted!

    def handle_error_rollback_fixed(self):
        """Fixed: restores both SWR cache and L0 snapshot from confirmed authoritative trip"""
        self.swr_cache = copy.deepcopy(self.confirmed_trip)
        self.l0_snapshot = copy.deepcopy(self.confirmed_trip)


def test_poc_3_itinerary_rollback_prevents_corrupted_snapshot():
    """證偽：樂觀更新異常時，若未執行 L0 快照校正回滾，本地離線儲存將殘留毒丸資料"""
    confirmed = {"id": "trip-1", "activities": ["Sensoji Temple"]}
    manager = MockItineraryDataManager(confirmed)

    # 模擬使用者編輯：樂觀寫入新活動
    optimistic = {"id": "trip-1", "activities": ["Sensoji Temple", "Tokyo Skytree (Unsaved)"]}
    manager.optimistic_update(optimistic, persist_to_l0_immediately=True)

    # 模擬 API 呼叫失敗拋出 500
    manager.handle_error_rollback_flawed()

    # 驗證缺陷：SWR 已回滾，但 L0 快照中殘留未被伺服器承認的 Skytree！
    assert "Tokyo Skytree (Unsaved)" in manager.l0_snapshot["activities"]
    assert "Tokyo Skytree (Unsaved)" not in manager.swr_cache["activities"]

    # 驗證修復：執行完整回滾閉環
    manager.handle_error_rollback_fixed()
    assert manager.l0_snapshot["activities"] == ["Sensoji Temple"]
    assert manager.swr_cache["activities"] == ["Sensoji Temple"]
