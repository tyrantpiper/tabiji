#!/usr/bin/env python3
"""
scripts/backfill_users.py
=========================
Backfill legacy user UUIDs from itineraries and trip_members into public.users.
Prevents existing users from being treated as unknown during silent session exchange.
"""

import os
import re
import sys
from pathlib import Path

# Add backend directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(REPO_ROOT / "backend" / ".env")

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

UUID_V4_REGEX = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
    re.IGNORECASE
)

def run_backfill():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("[ERROR] Missing Supabase credentials in backend/.env")
        sys.exit(1)

    sb = create_client(url, key)

    print("[INFO] Fetching existing users from public.users...")
    existing_users = set(u["id"] for u in sb.table("users").select("id").execute().data or [])
    print(f"   Existing users count: {len(existing_users)}")

    print("[INFO] Fetching creators from itineraries...")
    creators = sb.table("itineraries").select("created_by, creator_name").execute().data or []
    print(f"   Total itineraries: {len(creators)}")

    print("[INFO] Fetching members from trip_members...")
    members = sb.table("trip_members").select("user_id, user_name").execute().data or []
    print(f"   Total trip_members: {len(members)}")

    to_insert = {}

    for c in creators:
        uid = str(c.get("created_by") or "").strip().lower()
        if UUID_V4_REGEX.match(uid) and uid not in existing_users and uid not in to_insert:
            to_insert[uid] = str(c.get("creator_name") or "Traveler").strip() or "Traveler"

    for m in members:
        uid = str(m.get("user_id") or "").strip().lower()
        if UUID_V4_REGEX.match(uid) and uid not in existing_users and uid not in to_insert:
            to_insert[uid] = str(m.get("user_name") or "Traveler").strip() or "Traveler"

    print(f"[INFO] Total orphaned valid UUIDs to backfill: {len(to_insert)}")

    if not to_insert:
        print("[SUCCESS] No orphaned users to backfill. All valid UUIDs exist in public.users.")
        return 0

    payload = [{"id": uid, "name": name} for uid, name in to_insert.items()]
    chunk_size = 50
    inserted_count = 0

    for i in range(0, len(payload), chunk_size):
        chunk = payload[i:i + chunk_size]
        try:
            res = sb.table("users").upsert(chunk, on_conflict="id", ignore_duplicates=True).execute()
            inserted_count += len(res.data or [])
            print(f"   Upserted chunk {i // chunk_size + 1}/{(len(payload) + chunk_size - 1) // chunk_size} ({len(chunk)} users)")
        except Exception as e:
            print(f"[WARN] Chunk upsert error: {e}")
            # Fallback to single insertion for error isolation
            for single in chunk:
                try:
                    sb.table("users").upsert(single, on_conflict="id", ignore_duplicates=True).execute()
                    inserted_count += 1
                except Exception as single_err:
                    print(f"   Failed to insert {single['id']}: {single_err}")

    # Re-verify total users
    final_users = sb.table("users").select("id").execute().data or []
    print(f"[SUCCESS] Backfill Complete! Users before: {len(existing_users)} -> Users after: {len(final_users)}")
    return 0

if __name__ == "__main__":
    sys.exit(run_backfill())
