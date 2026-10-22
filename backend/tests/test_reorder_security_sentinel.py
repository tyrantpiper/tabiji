import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from pydantic import BaseModel
from typing import List, Optional

class ReorderItem(BaseModel):
    item_id: str
    sort_order: int
    time_slot: Optional[str] = None

class ReorderRequest(BaseModel):
    items: List[ReorderItem]
    adjust_times: bool = False

def vulnerable_reorder_logic(request: ReorderRequest, user_id: str, supabase: MagicMock):
    """Vulnerable implementation: only validates items[0] and updates by item_id without itinerary_id scoping"""
    if request.items:
        first_item = supabase.table("itinerary_items").select("itinerary_id").eq("id", request.items[0].item_id).single().execute()
        if first_item.data:
            tid = first_item.data["itinerary_id"]
            member_check = supabase.table("trip_members").select("user_id").eq("itinerary_id", tid).eq("user_id", user_id).execute()
            if not member_check.data:
                raise HTTPException(status_code=403, detail="您沒有權限排序此行程")

    results = []
    for item in request.items:
        data = {"sort_order": item.sort_order}
        # VULNERABILITY: updates by id only, allowing cross-tenant item mutation
        res = supabase.table("itinerary_items").update(data).eq("id", item.item_id).execute()
        results.append({"id": item.item_id, "updated": bool(res.data)})
    return results

def secured_reorder_logic(request: ReorderRequest, user_id: str, supabase: MagicMock):
    """Secured implementation: validates ALL items belong to the authorized itinerary_id and scopes update"""
    if not request.items:
        return []

    item_ids = [i.item_id for i in request.items]
    items_query = supabase.table("itinerary_items").select("id, itinerary_id").in_("id", item_ids).execute()
    db_items = items_query.data or []
    
    if len(db_items) != len(item_ids):
        raise HTTPException(status_code=404, detail="部分項目不存在")

    itinerary_ids = {row["itinerary_id"] for row in db_items}
    if len(itinerary_ids) != 1:
        raise HTTPException(status_code=400, detail="禁止跨行程批次排序")

    tid = itinerary_ids.pop()
    member_check = supabase.table("trip_members").select("user_id").eq("itinerary_id", tid).eq("user_id", user_id).execute()
    if not member_check.data:
        raise HTTPException(status_code=403, detail="您沒有權限排序此行程")

    results = []
    for item in request.items:
        data = {"sort_order": item.sort_order}
        if request.adjust_times and item.time_slot:
            data["time_slot"] = item.time_slot
        # SECURED: Scoped to authorized itinerary_id
        res = supabase.table("itinerary_items").update(data).eq("id", item.item_id).eq("itinerary_id", tid).execute()
        results.append({"id": item.item_id, "updated": bool(res.data)})
    return results

def test_vulnerable_reorder_permits_cross_tenant_item_tampering():
    """Prove that vulnerable reorder permits updating victim's item when attacker's item is placed at index 0"""
    mock_supabase = MagicMock()
    
    # Attacker owns trip_A with item_A; victim owns trip_B with item_B
    attacker_user_id = "user-attacker"
    
    # Mock first_item query (item_A -> trip_A)
    first_item_res = MagicMock()
    first_item_res.data = {"itinerary_id": "trip_A"}
    
    # Mock member_check query (attacker is member of trip_A)
    member_check_res = MagicMock()
    member_check_res.data = [{"user_id": attacker_user_id}]
    
    # Mock update query (both items successfully updated in DB)
    update_res = MagicMock()
    update_res.data = [{"id": "updated"}]

    def mock_table(table_name):
        mock_t = MagicMock()
        if table_name == "itinerary_items":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = first_item_res
            mock_t.update.return_value.eq.return_value.execute.return_value = update_res
        elif table_name == "trip_members":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = member_check_res
        return mock_t

    mock_supabase.table.side_effect = mock_table

    # Malicious payload: Attacker's item at index 0, Victim's item at index 1
    malicious_req = ReorderRequest(
        items=[
            ReorderItem(item_id="attacker-item-1", sort_order=0),
            ReorderItem(item_id="victim-item-999", sort_order=999) # CROSS-TENANT ITEM!
        ]
    )

    # Vulnerable logic executes without exception and updates BOTH items
    results = vulnerable_reorder_logic(malicious_req, attacker_user_id, mock_supabase)
    assert len(results) == 2
    assert results[1]["id"] == "victim-item-999"
    assert results[1]["updated"] is True

def test_secured_reorder_blocks_cross_tenant_item_tampering():
    """Prove that secured reorder detects and rejects cross-tenant items with 400 Bad Request"""
    mock_supabase = MagicMock()
    attacker_user_id = "user-attacker"

    # Mock DB query returning items from different itineraries
    items_query_res = MagicMock()
    items_query_res.data = [
        {"id": "attacker-item-1", "itinerary_id": "trip_A"},
        {"id": "victim-item-999", "itinerary_id": "trip_B"} # Different itinerary!
    ]

    mock_t = MagicMock()
    mock_t.select.return_value.in_.return_value.execute.return_value = items_query_res
    mock_supabase.table.return_value = mock_t

    malicious_req = ReorderRequest(
        items=[
            ReorderItem(item_id="attacker-item-1", sort_order=0),
            ReorderItem(item_id="victim-item-999", sort_order=999)
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        secured_reorder_logic(malicious_req, attacker_user_id, mock_supabase)

    assert exc_info.value.status_code == 400
    assert "禁止跨行程批次排序" in exc_info.value.detail
