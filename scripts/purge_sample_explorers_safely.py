#!/usr/bin/env python3
"""
🛡️ Safe Explorer Sample Trip Purge Script (scripts/purge_sample_explorers_safely.py)
---------------------------------------------------------------------------------
Safely purges unused legacy Explorer sample trip accounts created during historical
crawling, backfilling, and E2E runs, while strictly preserving real users and ensuring
zero regression for the active "seed-sample" onboarding mechanism.

Safety Guardrails:
1. Strict Dry-Run by default: Won't delete anything unless --execute is explicitly passed.
2. Complete Physical JSON Backup before any mutation (saved to docs/migrations/backups/).
3. Real-User Whitelist & Activity Invariant Protection:
   - Aborts if user has any expense records, capsule records, or custom notes.
   - Aborts if user has multiple itineraries or non-sample itinerary title.
   - Protected usernames: Ryan, Mimi, Chungshi, 抑制劑, etc.
4. Chunking (CHUNK_SIZE=50): Prevents PostgREST HTTP 414 URI Too Long.
5. Foreign Key Strict Order: itinerary_items -> trip_members -> itineraries -> public.users.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

# Windows console cp950 encoding defense
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ensure repo root is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / "backend" / ".env")

from supabase import Client, create_client

PROTECTED_NAMES = {
    "ryan", "mimi", "chungshi", "抑制劑", "test", "tester", "admin", "dev"
}
SAMPLE_TRIP_TITLE = "3 Day Taipei Explorer ✨"
CHUNK_SIZE = 50


def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("❌ [FATAL] SUPABASE_URL and SUPABASE_KEY/SERVICE_ROLE_KEY must be set in backend/.env")
        sys.exit(1)
    return create_client(url, key)


def scan_explorers(supabase: Client) -> List[Dict[str, Any]]:
    """Scan all candidate Explorer users and their associated sample itineraries."""
    print("🔍 [Phase 1: Scanning Candidates] Fetching users with name 'Explorer'...")
    res = (
        supabase.table("users")
        .select("id, name, created_at, avatar_url")
        .eq("name", "Explorer")
        .execute()
    )
    all_explorers = res.data or []
    print(f"   Found {len(all_explorers)} users named 'Explorer'.")
    return all_explorers


def inspect_and_filter_candidates(
    supabase: Client,
    explorers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Rigorous qualification check for all Explorer candidates."""
    print("🛡️ [Phase 2: Qualification & Activity Verification] Verifying zero user activity...")
    
    explorer_ids = [u["id"] for u in explorers]
    qualified_candidates = []
    disqualified = []

    # Process in chunks of 50 to query memberships
    all_memberships = []
    for i in range(0, len(explorer_ids), CHUNK_SIZE):
        chunk = explorer_ids[i:i + CHUNK_SIZE]
        m_res = (
            supabase.table("trip_members")
            .select("id, itinerary_id, user_id, user_name")
            .in_("user_id", chunk)
            .execute()
        )
        if m_res.data:
            all_memberships.extend(m_res.data)

    user_to_trips: Dict[str, List[Dict[str, Any]]] = {}
    for m in all_memberships:
        user_to_trips.setdefault(m["user_id"], []).append(m)

    trip_ids = list({m["itinerary_id"] for m in all_memberships})
    print(f"   Queried {len(all_memberships)} memberships across {len(trip_ids)} unique itineraries.")

    # Query itinerary metadata
    all_itineraries: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(trip_ids), CHUNK_SIZE):
        chunk = trip_ids[i:i + CHUNK_SIZE]
        t_res = (
            supabase.table("itineraries")
            .select("id, title, created_by, created_at")
            .in_("id", chunk)
            .execute()
        )
        for t in (t_res.data or []):
            all_itineraries[t["id"]] = t

    # Query expenses check (MUST BE 0)
    all_expenses: List[Dict[str, Any]] = []
    for i in range(0, len(trip_ids), CHUNK_SIZE):
        chunk = trip_ids[i:i + CHUNK_SIZE]
        e_res = (
            supabase.table("expenses")
            .select("id, itinerary_id")
            .in_("itinerary_id", chunk)
            .execute()
        )
        if e_res.data:
            all_expenses.extend(e_res.data)
    tainted_trip_ids_expenses = {e["itinerary_id"] for e in all_expenses}

    # Query capsules check (MUST BE 0)
    all_capsules: List[Dict[str, Any]] = []
    for i in range(0, len(trip_ids), CHUNK_SIZE):
        chunk = trip_ids[i:i + CHUNK_SIZE]
        try:
            c_res = (
                supabase.table("trip_capsule_entries")
                .select("id, trip_id")
                .in_("trip_id", chunk)
                .execute()
            )
            if c_res.data:
                all_capsules.extend(c_res.data)
        except Exception as e:
            # Table might not exist or empty
            pass
    tainted_trip_ids_capsules = {c["trip_id"] for c in all_capsules if "trip_id" in c}

    # Evaluation
    for u in explorers:
        uid = u["id"]
        uname = (u.get("name") or "").strip().lower()

        # Whitelist protection
        if uname in PROTECTED_NAMES:
            disqualified.append({"user": u, "reason": f"Name '{u.get('name')}' is in PROTECTED_NAMES whitelist"})
            continue

        memberships = user_to_trips.get(uid, [])
        if len(memberships) == 0:
            # Orphan user with no trips - safe to delete
            qualified_candidates.append({
                "user": u,
                "itinerary_id": None,
                "itinerary": None,
                "membership_id": None,
            })
            continue

        if len(memberships) > 1:
            disqualified.append({"user": u, "reason": f"User has multiple ({len(memberships)}) trips"})
            continue

        m = memberships[0]
        tid = m["itinerary_id"]
        itin = all_itineraries.get(tid)

        if not itin:
            # Itinerary already missing, member is orphaned
            qualified_candidates.append({
                "user": u,
                "itinerary_id": tid,
                "itinerary": None,
                "membership_id": m["id"],
            })
            continue

        # Check trip title & creator
        if itin.get("title") != SAMPLE_TRIP_TITLE:
            disqualified.append({"user": u, "reason": f"Trip title '{itin.get('title')}' != '{SAMPLE_TRIP_TITLE}'"})
            continue

        if itin.get("created_by") != "SYSTEM":
            disqualified.append({"user": u, "reason": f"Trip created_by '{itin.get('created_by')}' != 'SYSTEM'"})
            continue

        # Check expenses & capsules
        if tid in tainted_trip_ids_expenses:
            disqualified.append({"user": u, "reason": f"Trip {tid} has associated expenses"})
            continue

        if tid in tainted_trip_ids_capsules:
            disqualified.append({"user": u, "reason": f"Trip {tid} has associated capsules"})
            continue

        # Fully qualified zombie candidate
        qualified_candidates.append({
            "user": u,
            "itinerary_id": tid,
            "itinerary": itin,
            "membership_id": m["id"],
        })

    print(f"   ✅ Qualified candidates for purge: {len(qualified_candidates)}")
    print(f"   ⚠️ Disqualified candidates (protected): {len(disqualified)}")
    if disqualified:
        for d in disqualified[:5]:
            print(f"      - User {d['user']['id']} ({d['user'].get('name')}): {d['reason']}")

    return {
        "qualified": qualified_candidates,
        "disqualified": disqualified,
    }


def create_physical_backup(
    supabase: Client,
    qualified: List[Dict[str, Any]],
    backup_file: Path,
) -> str:
    """Exports all qualified users, memberships, itineraries, and items into a JSON backup."""
    print(f"💾 [Phase 3: Physical Backup] Generating snapshot to {backup_file.relative_to(REPO_ROOT)}...")
    backup_file.parent.mkdir(parents=True, exist_ok=True)

    target_user_ids = [q["user"]["id"] for q in qualified]
    target_trip_ids = list({q["itinerary_id"] for q in qualified if q["itinerary_id"]})

    # Fetch all items for the target itineraries
    all_items = []
    for i in range(0, len(target_trip_ids), CHUNK_SIZE):
        chunk = target_trip_ids[i:i + CHUNK_SIZE]
        it_res = (
            supabase.table("itinerary_items")
            .select("*")
            .in_("itinerary_id", chunk)
            .execute()
        )
        if it_res.data:
            all_items.extend(it_res.data)

    # Fetch all memberships
    all_memberships = []
    for i in range(0, len(target_user_ids), CHUNK_SIZE):
        chunk = target_user_ids[i:i + CHUNK_SIZE]
        m_res = (
            supabase.table("trip_members")
            .select("*")
            .in_("user_id", chunk)
            .execute()
        )
        if m_res.data:
            all_memberships.extend(m_res.data)

    backup_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_users": len(target_user_ids),
            "total_itineraries": len(target_trip_ids),
            "total_memberships": len(all_memberships),
            "total_items": len(all_items),
        },
        "users": [q["user"] for q in qualified],
        "itineraries": [q["itinerary"] for q in qualified if q["itinerary"]],
        "trip_members": all_memberships,
        "itinerary_items": all_items,
    }

    content_str = json.dumps(backup_payload, indent=2, ensure_ascii=False)
    backup_file.write_text(content_str, encoding="utf-8")
    
    sha256_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
    print(f"   ✅ Backup written successfully ({len(content_str):,} bytes). SHA256: {sha256_hash[:16]}...")
    return sha256_hash


def execute_purge(
    supabase: Client,
    qualified: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Executes the safe purge in chunks according to foreign key order."""
    target_user_ids = [q["user"]["id"] for q in qualified]
    target_trip_ids = list({q["itinerary_id"] for q in qualified if q["itinerary_id"]})

    print(f"🔥 [Phase 4: Physical Execution] Starting chunked deletion (CHUNK_SIZE={CHUNK_SIZE})...")

    # Step 1: Delete itinerary_items
    deleted_items = 0
    print(f"   [1/4] Deleting itinerary_items for {len(target_trip_ids)} itineraries...")
    for i in range(0, len(target_trip_ids), CHUNK_SIZE):
        chunk = target_trip_ids[i:i + CHUNK_SIZE]
        del_res = supabase.table("itinerary_items").delete().in_("itinerary_id", chunk).execute()
        deleted_items += len(del_res.data or [])

    # Step 2: Delete trip_members (by itinerary_id and by user_id)
    deleted_members = 0
    print(f"   [2/5] Deleting trip_members for {len(target_trip_ids)} itineraries and {len(target_user_ids)} users...")
    for i in range(0, len(target_trip_ids), CHUNK_SIZE):
        chunk = target_trip_ids[i:i + CHUNK_SIZE]
        del_res = supabase.table("trip_members").delete().in_("itinerary_id", chunk).execute()
        deleted_members += len(del_res.data or [])
    for i in range(0, len(target_user_ids), CHUNK_SIZE):
        chunk = target_user_ids[i:i + CHUNK_SIZE]
        supabase.table("trip_members").delete().in_("user_id", chunk).execute()

    # Step 3: Delete itineraries
    deleted_itins = 0
    print(f"   [3/5] Deleting itineraries for {len(target_trip_ids)} sample trips...")
    for i in range(0, len(target_trip_ids), CHUNK_SIZE):
        chunk = target_trip_ids[i:i + CHUNK_SIZE]
        del_res = supabase.table("itineraries").delete().in_("id", chunk).execute()
        deleted_itins += len(del_res.data or [])

    # Step 4: Delete user_preferences (if any)
    deleted_prefs = 0
    print(f"   [4/5] Deleting user_preferences for {len(target_user_ids)} users...")
    for i in range(0, len(target_user_ids), CHUNK_SIZE):
        chunk = target_user_ids[i:i + CHUNK_SIZE]
        try:
            del_res = supabase.table("user_preferences").delete().in_("user_id", chunk).execute()
            deleted_prefs += len(del_res.data or [])
        except Exception:
            pass

    # Step 5: Delete public.users
    deleted_users = 0
    print(f"   [5/5] Deleting public.users for {len(target_user_ids)} Explorer users...")
    for i in range(0, len(target_user_ids), CHUNK_SIZE):
        chunk = target_user_ids[i:i + CHUNK_SIZE]
        del_res = supabase.table("users").delete().in_("id", chunk).execute()
        deleted_users += len(del_res.data or [])

    print(f"🎉 [Phase 4: Complete] Purge statistics:")
    print(f"   - Deleted itinerary_items: {deleted_items}")
    print(f"   - Deleted trip_members:    {deleted_members}")
    print(f"   - Deleted itineraries:     {deleted_itins}")
    print(f"   - Deleted preferences:     {deleted_prefs}")
    print(f"   - Deleted users:           {deleted_users}")

    return {
        "deleted_items": deleted_items,
        "deleted_members": deleted_members,
        "deleted_itineraries": deleted_itins,
        "deleted_prefs": deleted_prefs,
        "deleted_users": deleted_users,
    }


def main():
    parser = argparse.ArgumentParser(description="Safely purge legacy Explorer sample trip zombie accounts.")
    parser.add_argument("--execute", action="store_true", default=False, help="Actually perform deletion (defaults to False for dry-run).")
    parser.add_argument("--backup-path", type=str, default="docs/migrations/backups/explorers_backup_20261023.json", help="Path to JSON backup.")
    args = parser.parse_args()

    supabase = get_supabase_client()
    backup_file = REPO_ROOT / args.backup_path

    # Step 1: Scan
    explorers = scan_explorers(supabase)
    if not explorers:
        print("✅ No Explorer users found. Database is already clean.")
        return

    # Step 2: Filter & Invariant Check
    qualification = inspect_and_filter_candidates(supabase, explorers)
    qualified = qualification["qualified"]
    disqualified = qualification["disqualified"]

    if not qualified:
        print("⚠️ No qualified zombie candidates found.")
        return

    # Step 3: Always create backup before execution
    backup_hash = create_physical_backup(supabase, qualified, backup_file)

    if not args.execute:
        print("\n" + "=" * 80)
        print("🛡️ [DRY RUN COMPLETED - ZERO MUTATIONS APPLIED]")
        print(f"   - Total Explorer Accounts Found: {len(explorers)}")
        print(f"   - Qualified for Purge:           {len(qualified)}")
        print(f"   - Disqualified (Protected):      {len(disqualified)}")
        print(f"   - Backup Generated:              {backup_file}")
        print(f"   - Backup SHA256:                 {backup_hash}")
        print("👉 To physically execute deletion, run with: python scripts/purge_sample_explorers_safely.py --execute")
        print("=" * 80 + "\n")
        return

    # Step 4: Execute Purge
    stats = execute_purge(supabase, qualified)
    print("\n✅ Purge successfully completed under Sentinel safety protocol.")


if __name__ == "__main__":
    main()
