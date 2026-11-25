#!/usr/bin/env python3
"""
🛡️ Tabidachi Fixed Test Pool & Orphan Account Lifecycle Manager
(scripts/manage_test_accounts.py)
---------------------------------------------------------------------------
Unified operations CLI for auditing, safely purging approved test/orphan
accounts, and upgrading the fixed 6-account dual-track test pool.

Safety Invariants:
1. Strict Dry-Run by default for --purge and --upgrade-pool; requires explicit --execute.
2. Full-table paginated reads (PAGE_SIZE=1000) to prevent PostgREST max_rows truncation.
3. Hard-protected accounts matched via SHA-256 digests (main account + 6-account test pool);
   plaintext personal QA UUID is never embedded in public source code.
4. --purge strictly targets the human-approved 36-char UUID list and explicit orphan classes,
   checking both itineraries.created_by and itineraries.user_id (fk_itineraries_user CASCADE),
   enforcing created_by == 'SYSTEM' + 1h cooldown for empty sample trips, and filtering non-UUIDs
   before querying UUID-typed columns (preventing Postgres 22P02).
5. Row-level trigger throttling: itinerary_items and itineraries are deleted by id in batches of
   <= 25 rows with 0.3s sleep between batches to protect pg_net -> cleanup-cloudinary triggers.
6. Redacted physical JSON backups locked inside docs/migrations/backups/ with explicit non-sensitive
   column selects, recursive sensitive-key stripping, and bare `git check-ignore -q` verification.
7. Explicit Cloudinary destroy verification requiring HTTP 200 and result in {"ok", "not found"}.
8. --upgrade-pool hard-skips VIEWER (00003) and RYAN_TEST, warms up /api/health/deep, uses timeout=30.0,
   strictly validates upgraded response, writes atomically via same-dir .env.test-pool.tmp.local +
   os.replace with bare `git check-ignore -q` protection, and probes Supabase on timeout to detect
   PARTIAL_UPGRADE_DESYNC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote, unquote, urlparse

# Windows console cp950 encoding defense
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
for _p in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from supabase import Client, create_client  # noqa: E402

from backend.tests.fixtures.test_users import (  # noqa: E402
    LEGACY_PINNED_TEST_USER_IDS,
    MODERN_UPGRADEABLE_TEST_USER_IDS,
    STATIC_ROLE_TEST_USER_IDS,
    SYNTHETIC_RYAN_TEST_ID,
    TEST_USERS,
    TEST_USER_CAPSULE_ID,
    TEST_USER_EDITOR_ID,
    TEST_USER_OWNER_ID,
    TEST_USER_STRANGER_ID,
    TEST_USER_VIEWER_ID,
)

# ---------------------------------------------------------------------------
# Constants & Regexes
# ---------------------------------------------------------------------------
PAGE_SIZE = 1000
CHUNK_SIZE = 50
TRIGGER_BATCH_SIZE = 25
TRIGGER_BATCH_SLEEP_SEC = 0.3
UPGRADE_REQUEST_TIMEOUT_SEC = 30.0
UPGRADE_REQUEST_SPACING_SEC = 0.5
SYSTEM_COOLDOWN_HOURS = 1.0
DEFAULT_API_BASE = "https://www.tabijiapp.com"
DEFAULT_ENV_OUT = ".env.test-pool.local"
USER_AGENT = "Tabiji-TestPool-Manager/1.0"
SAMPLE_TRIP_TITLE = "3 Day Taipei Explorer ✨"

BACKUPS_DIR = REPO_ROOT / "docs" / "migrations" / "backups"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
RFC4122_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
TBJ_REC_RE = re.compile(
    r"^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$",
    re.IGNORECASE,
)

SENSITIVE_BACKUP_FIELDS: frozenset[str] = frozenset(
    {
        "recovery_secret_hash",
        "recovery_key_encrypted",
        "recovery_key_id",
        "p256dh",
        "auth",
    }
)


def sha256_uid(uid: str) -> str:
    return hashlib.sha256(str(uid or "").strip().lower().encode("utf-8")).hexdigest()


# SHA-256 digests of production main account and personal QA pool account (no plaintext personal UUIDs in source)
MAIN_USER_UID_SHA256 = "1b9110f155d92fc3cee7dba9833489dd1e29c5ee57b54fafb7d7ed6b5e100d2d"
RYAN_TEST_UID_SHA256 = "df53a6abe0fa38b52ecf55f21d794ac5d47e6d370af2c6ac7d6f6d3c829e0c29"

HARD_PROTECTED_USER_ID_HASHES: frozenset[str] = frozenset(
    {
        MAIN_USER_UID_SHA256,
        RYAN_TEST_UID_SHA256,
        *(sha256_uid(uid) for uid in STATIC_ROLE_TEST_USER_IDS),
        sha256_uid(SYNTHETIC_RYAN_TEST_ID),
    }
)

# Legacy-pinned role that must NEVER be upgraded to tbj_rec_*
LEGACY_PINNED_TEST_IDS: frozenset[str] = frozenset(
    uid.lower() for uid in LEGACY_PINNED_TEST_USER_IDS
)

# Ordered 4-role upgrade queue (00001, 00002, 00004, 00005)
UPGRADE_POOL_ROLES: Tuple[Tuple[str, str], ...] = (
    ("OWNER", TEST_USER_OWNER_ID),
    ("EDITOR", TEST_USER_EDITOR_ID),
    ("CAPSULE", TEST_USER_CAPSULE_ID),
    ("STRANGER", TEST_USER_STRANGER_ID),
)

# Human-approved 29 explicit 36-char test/clone user UUIDs eligible for --purge
APPROVED_PURGE_USER_IDS: Tuple[str, ...] = (
    "82f4d62f-5388-416f-b54a-b4ebb7ea2266",  # #1  Test
    "42082222-7750-4966-bca6-4962e69945e7",  # #2  QA_Audit
    "9663cbe4-5ca0-4608-bc61-37ae85a527e7",  # #3  test
    "9106c7c0-3b9a-457e-8735-3be066e019f7",  # #4  SentinelTest
    "e56b5797-01ef-4c02-80ae-8d8451215620",  # #5  Ryan (test clone)
    "2ccd0fb6-ad40-4a56-9e6e-580012e1ae1d",  # #6  test
    "4646d35e-f48b-4136-8a82-7487f854100c",  # #7  ryan (test clone)
    "0880233b-b8d8-4d2d-a50c-7cd490f12b02",  # #8  ryan (test clone)
    "e3797b4f-5271-4a12-8172-337d47ded83b",  # #9  Ryan (test clone)
    "322a29ac-edfe-44d7-823e-496a8db31c64",  # #10 ryan (historical clone)
    "c9869ff3-fe39-412a-b952-bd858e7bdfb5",  # #11 Test User
    "5e762c9f-f857-43bb-ba5e-7a64eb0b24f9",  # #12 Returned Traveler
    "c4fa2b0d-26bb-485b-95e4-60d97b0200c1",  # #13 Returned Traveler
    "75788120-4f43-42aa-97a9-f8334bf78247",  # #14 Ryan (test clone)
    "a2823f99-35b1-4897-8a0a-0326a7f7c9f3",  # #15 Test
    "843e3729-d660-46a2-b4b7-b2dd4ccce717",  # #16 Ryan (historical clone)
    "cf4349b0-14a8-40e0-8224-5e6eaa64dfb4",  # #17 Test
    "754fbbf6-3a81-456f-a066-8a4b8bbb5be9",  # #18 Traveler Test
    "66666666-6666-6666-6666-666666666666",  # #19 Auditor
    "1fd4901e-9cbc-4c0c-b0eb-12d92908760c",  # #20 Test
    "ea7c2f75-f12e-4e43-8a2c-20c4c6035ef2",  # #21 QA_Test
    "689b3808-eb50-4395-97b3-57b42ddff6bf",  # #22 Verification Ryan
    "799d5322-b85c-4800-9ab9-e8dadd28cff9",  # #23 Trace Test
    "31ce7407-49ba-48e6-8100-541082d09bea",  # #24 Test User
    "89bb71c5-0086-47b2-81af-7b3cbcfb1563",  # #25 Test User
    "ae44fb92-dae6-40ca-b6c3-34f9f8fe3c4c",  # #26 First Name
    "98784529-bdbf-4313-b1d1-11a960d8bfa1",  # #27 Final Debug Tester
    "f55e24fd-6f18-4a4e-9163-5566cfcc64c2",  # #28 Valid Tester
    "daec9523-d377-4752-bed8-17efe5bba1e5",  # #29 開發者
)

# Approved non-UUID test itinerary creators (2025-12 legacy test artifacts)
APPROVED_NON_UUID_CREATORS: frozenset[str] = frozenset(
    {
        "test-uuid",
        "test-uuid-123",
        "audit_user_2df9dd54",
        "test_user_frontend_verify",
    }
)

# Explicit guardrail exemption (b): [Test] Editor (00002) dangling membership on retired TEST-FULL-FLOW
EXEMPT_ORPHAN_TRIP_MEMBERSHIPS: frozenset[Tuple[str, str]] = frozenset(
    {
        (
            "f4a1773d-582b-413a-8a1f-a27b9dfde549",
            TEST_USER_EDITOR_ID.lower(),
        ),
    }
)

# Suspect name regex for read-only --audit drift detection (never auto-purged)
SUSPECT_TEST_NAME_RE = re.compile(
    r"(?:^|\b)(?:test|tester|qa|audit|auditor|sentinel|debug|verify|verification|bot)(?:\b|_|\d|$)",
    re.IGNORECASE,
)

# Explicit non-sensitive column selections for backup / queries
SAFE_SELECT_COLS: Dict[str, str] = {
    "users": "id, name, avatar_url, email, created_at, credential_version",
    "itineraries": "id, title, created_by, user_id, start_date, end_date, public_id, created_at",
    "itinerary_items": "id, itinerary_id, day_number, sort_order, place_name, category, time_slot, created_at",
    "trip_members": "id, itinerary_id, user_id, user_name, created_at",
    "expenses": "id, itinerary_id, title, amount, currency, created_by, payer_id, created_at",
    "trip_capsule_entries": "id, trip_id, author_id, photo_url, created_at",
    "user_preferences": "id, user_id, category, updated_at",
    "notifications": "id, user_id, title, created_at",
    "push_subscriptions": "id, user_id, endpoint, created_at",
}

# Cloudinary URL parsing helpers (mirroring backend/routers/users.py)
_SINGLE_TRANSFORM_SEGMENT_RE = re.compile(
    r"^(?:[wh]_\d+(?:\.\d+)?|c_(?:scale|fit|limit|mfit|fill|lfill|pad|lpad|mpad|fill_pad|crop|thumb|imagga_crop|imagga_scale)|q_(?:auto(?::(?:best|good|eco|low))?|\d+(?::\d+)?)|f_(?:auto|webp|avif|jpg|jpeg|png|gif|svg|pdf|mp4|webm)|dpr_(?:auto|\d+(?:\.\d+)?)|g_(?:auto(?::[a-z_]+)?|face|faces|center|north|south|east|west|north_east|north_west|south_east|south_west)|fl_[a-z0-9_.:-]+|e_[a-z0-9_.:-]+|ar_\d+(?::\d+|\.\d+)?|r_(?:max|\d+(?::\d+)*)|a_(?:-?\d+|auto_(?:right|left)|ignore|exif|hflip|vflip)|o_\d+|bo_[^,/]+|co_(?:rgb:[0-9a-fA-F]{3,8}|[a-z]+)|t_[a-zA-Z0-9_-]+|b_(?:auto(?::[a-z_]+)?|rgb:[0-9a-fA-F]{3,8}|[a-z]+))$"
)
_SAFE_PUBLIC_ID_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")
_VERSION_SEGMENT_RE = re.compile(r"^v\d+$")
_CLOUD_UPLOAD_PATH_RE = re.compile(r"^/([^/]+)/(image|video|raw)/upload/(.+)$")
_RESOURCE_UPLOAD_PATH_RE = re.compile(r"^/(image|video|raw)/upload/(.+)$")
_BARE_UPLOAD_PATH_RE = re.compile(r"^/upload/(.+)$")


class PartialUpgradeDesyncError(RuntimeError):
    """Raised when POST /api/auth/session timed out but Supabase already recorded recovery_key_id."""


# ---------------------------------------------------------------------------
# Pure Helpers & Guardrails
# ---------------------------------------------------------------------------
def is_valid_uuid(val: Any) -> bool:
    return isinstance(val, str) and bool(UUID_RE.match(val.strip()))


def uuid_only(values: Iterable[Any]) -> List[str]:
    """Return deduplicated lowercase valid UUIDs only (prevents Postgres 22P02 on UUID columns)."""
    seen: Set[str] = set()
    out: List[str] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip().lower()
        if cleaned and UUID_RE.match(cleaned) and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def unique_strings(values: Iterable[Any]) -> List[str]:
    """Return deduplicated non-empty trimmed strings preserving order."""
    seen: Set[str] = set()
    out: List[str] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _get_env_ryan_test_id() -> str:
    """Read RYAN_TEST UUID from env vars, ignoring whitespace-only entries."""
    for env_name in ("TEST_USER_RYAN_TEST_ID", "NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID"):
        val = (os.getenv(env_name) or "").strip()
        if val:
            return val.lower()
    return ""


def is_hard_protected_user(uid: Any) -> bool:
    """Check whether a user ID matches the SHA-256 hard-protected whitelist (main + 6-account pool)."""
    if not isinstance(uid, str):
        return False
    cleaned = uid.strip().lower()
    if not cleaned:
        return False
    digest = sha256_uid(cleaned)
    if digest in HARD_PROTECTED_USER_ID_HASHES:
        return True
    env_ryan = _get_env_ryan_test_id()
    if env_ryan and sha256_uid(env_ryan) == digest:
        return True
    return False


def mask_recovery_key(key: str) -> str:
    """Mask recovery key for safe stdout logging (never emit plaintext secret)."""
    cleaned = (key or "").strip()
    if len(cleaned) <= 16:
        return "tbj_rec_****"
    return f"{cleaned[:12]}****...****{cleaned[-4:]}"


def parse_iso_timestamp(val: Any) -> Optional[datetime]:
    if not isinstance(val, str) or not val.strip():
        return None
    raw = val.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def strip_sensitive_fields(obj: Any) -> Any:
    """Recursively strip all credential / push-subscription secrets from backup structures."""
    if isinstance(obj, dict):
        return {
            k: strip_sensitive_fields(v)
            for k, v in obj.items()
            if k not in SENSITIVE_BACKUP_FIELDS
        }
    if isinstance(obj, list):
        return [strip_sensitive_fields(item) for item in obj]
    return obj


def resolve_safe_backup_path(backup_path: str | Path, repo_root: Path = REPO_ROOT) -> Path:
    """
    Lock backup path strictly inside docs/migrations/backups/ using Path.resolve().is_relative_to()
    (AD-198 bidirectional path-traversal defense; forbids bare filenames and sibling-prefix escapes).
    """
    raw = Path(backup_path)
    if not raw.is_absolute():
        candidate = (repo_root / raw).resolve()
    else:
        candidate = raw.resolve()

    backups_root = (repo_root / "docs" / "migrations" / "backups").resolve()
    if not candidate.is_relative_to(backups_root) or candidate == backups_root:
        raise ValueError(
            f"Backup path '{backup_path}' MUST reside strictly inside '{backups_root}'."
        )
    if candidate.suffix.lower() != ".json":
        raise ValueError(f"Backup path '{backup_path}' MUST end with '.json'.")
    return candidate


def derive_atomic_tmp_path(env_out: Path) -> Path:
    """Derive a same-directory temporary path that remains covered by .env.*.local gitignore rules."""
    name = env_out.name
    if name.endswith(".local"):
        stem = name[: -len(".local")]
        return env_out.with_name(f"{stem}.tmp.local")
    return env_out.with_name(f"{name}.tmp.local")


def verify_git_ignored(target_path: Path, repo_root: Path = REPO_ROOT) -> bool:
    """
    Verify target_path is ignored by git using bare `git check-ignore -q <path>`
    (strictly WITHOUT `-v` or `--no-index`). Fail-closed on non-zero exit code.
    """
    resolved = target_path.resolve()
    root_resolved = repo_root.resolve()
    try:
        rel_arg = str(resolved.relative_to(root_resolved)).replace("\\", "/")
    except ValueError:
        rel_arg = str(resolved)

    proc = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel_arg],
        cwd=str(root_resolved),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def assert_git_ignored(target_path: Path, label: str, repo_root: Path = REPO_ROOT) -> None:
    if not verify_git_ignored(target_path, repo_root=repo_root):
        raise RuntimeError(
            f"🚨 [FAIL-CLOSED] {label} ('{target_path}') is NOT ignored by .gitignore "
            f"(verified via `git check-ignore -q`). Refusing to proceed."
        )


def _is_safe_public_id(val: Optional[str]) -> bool:
    if not isinstance(val, str):
        return False
    trimmed = val.strip()
    if not trimmed or len(trimmed) > 256:
        return False
    if ".." in trimmed or trimmed.startswith("/") or trimmed.endswith("/") or "//" in trimmed:
        return False
    if not _SAFE_PUBLIC_ID_RE.match(trimmed):
        return False
    return not any(seg in ("", ".", "..") for seg in trimmed.split("/"))


def _is_transform_segment(seg: str) -> bool:
    return "," in seg or bool(_SINGLE_TRANSFORM_SEGMENT_RE.match(seg))


def extract_cloudinary_asset(url: Optional[str]) -> Optional[Tuple[Optional[str], str, str]]:
    """Extract (cloud_name, resource_type, public_id) from a Cloudinary upload URL."""
    if not isinstance(url, str):
        return None
    trimmed = url.strip()
    if not trimmed:
        return None
    try:
        parsed = urlparse(trimmed)
        if parsed.scheme not in ("http", "https"):
            return None
        host = (parsed.hostname or "").lower().rstrip(".")
        if host != "res.cloudinary.com" and not host.endswith(".cloudinary.com"):
            return None

        pathname = unquote(parsed.path or "")
        url_cloud: Optional[str] = None
        resource_type = "image"
        remainder: Optional[str] = None

        m = _CLOUD_UPLOAD_PATH_RE.match(pathname)
        if m:
            url_cloud, resource_type, remainder = m.group(1), m.group(2), m.group(3)
        else:
            m = _RESOURCE_UPLOAD_PATH_RE.match(pathname)
            if m:
                resource_type, remainder = m.group(1), m.group(2)
            else:
                m = _BARE_UPLOAD_PATH_RE.match(pathname)
                if m:
                    remainder = m.group(1)

        if not remainder:
            return None

        segments = [seg for seg in remainder.split("/") if seg]
        if not segments:
            return None

        version_idx = next(
            (idx for idx, seg in enumerate(segments[:-1]) if _VERSION_SEGMENT_RE.match(seg)),
            -1,
        )
        if version_idx != -1:
            segments = segments[version_idx + 1 :]
        else:
            while len(segments) > 1 and _is_transform_segment(segments[0]):
                segments.pop(0)

        if not segments or (len(segments) == 1 and _VERSION_SEGMENT_RE.match(segments[0])):
            return None

        joined = "/".join(segments)
        public_id = joined if resource_type == "raw" else re.sub(r"\.[^./]+$", "", joined)
        if not _is_safe_public_id(public_id):
            return None
        return url_cloud, resource_type, public_id.strip()
    except Exception:
        return None


def get_cloudinary_config() -> Tuple[str, str, str]:
    cloud_name = (
        os.getenv("CLOUDINARY_CLOUD_NAME")
        or os.getenv("NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME")
        or ""
    ).strip()
    api_key = (
        os.getenv("CLOUDINARY_API_KEY")
        or os.getenv("NEXT_PUBLIC_CLOUDINARY_API_KEY")
        or ""
    ).strip()
    api_secret = (os.getenv("CLOUDINARY_API_SECRET") or "").strip()

    if not (cloud_name and api_key and api_secret):
        cloudinary_url = (os.getenv("CLOUDINARY_URL") or "").strip()
        if cloudinary_url:
            try:
                parsed = urlparse(cloudinary_url)
                if parsed.scheme == "cloudinary":
                    if not cloud_name and parsed.hostname:
                        cloud_name = unquote(parsed.hostname).strip()
                    if not api_key and parsed.username:
                        api_key = unquote(parsed.username).strip()
                    if not api_secret and parsed.password:
                        api_secret = unquote(parsed.password).strip()
            except Exception:
                pass
    return cloud_name, api_key, api_secret


# ---------------------------------------------------------------------------
# Environment & Paginated Supabase Access
# ---------------------------------------------------------------------------
def load_project_env() -> None:
    backend_env = REPO_ROOT / "backend" / ".env"
    if backend_env.exists():
        load_dotenv(backend_env, override=False)
    pool_env = REPO_ROOT / DEFAULT_ENV_OUT
    if pool_env.exists():
        load_dotenv(pool_env, override=False)


def get_supabase_client() -> Client:
    load_project_env()
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SECRET_KEY / SUPABASE_KEY must be set in backend/.env"
        )
    return create_client(url, key)


def fetch_all_rows(
    supabase: Client,
    table: str,
    columns: str,
    *,
    page_size: int = PAGE_SIZE,
    order_col: Optional[str] = "id",
) -> List[Dict[str, Any]]:
    """
    Full-table paginated reader (1,000 rows/page) to prevent PostgREST max_rows=1000 truncation.
    """
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        query = supabase.table(table).select(columns)
        if order_col:
            query = query.order(order_col)
        res = query.range(offset, offset + page_size - 1).execute()
        batch = res.data if isinstance(getattr(res, "data", None), list) else []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows


def fetch_rows_by_in_chunks(
    supabase: Client,
    table: str,
    columns: str,
    filter_col: str,
    values: Sequence[str],
    *,
    chunk_size: int = CHUNK_SIZE,
    page_size: int = PAGE_SIZE,
    order_col: Optional[str] = "id",
) -> List[Dict[str, Any]]:
    """Chunked `.in_()` reader (<= 50 items/query) with per-chunk pagination (<= 1000 rows/page)."""
    deduped = unique_strings(values)
    if not deduped:
        return []
    rows: List[Dict[str, Any]] = []
    for i in range(0, len(deduped), chunk_size):
        chunk = deduped[i : i + chunk_size]
        offset = 0
        while True:
            query = supabase.table(table).select(columns).in_(filter_col, chunk)
            if order_col:
                query = query.order(order_col)
            res = query.range(offset, offset + page_size - 1).execute()
            batch = res.data if isinstance(getattr(res, "data", None), list) else []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
    return rows


def load_database_snapshot(
    supabase: Client,
    *,
    include_auth_status: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Read-only full paginated snapshot across all relevant tables.
    Never selects recovery_secret_hash, recovery_key_encrypted, p256dh, or auth.
    Only includes recovery_key_id when include_auth_status=True (for --audit).
    """
    user_cols = (
        "id, name, avatar_url, email, created_at, recovery_key_id, credential_version"
        if include_auth_status
        else SAFE_SELECT_COLS["users"]
    )
    return {
        "users": fetch_all_rows(supabase, "users", user_cols),
        "itineraries": fetch_all_rows(supabase, "itineraries", SAFE_SELECT_COLS["itineraries"]),
        "trip_members": fetch_all_rows(supabase, "trip_members", SAFE_SELECT_COLS["trip_members"]),
        "expenses": fetch_all_rows(supabase, "expenses", SAFE_SELECT_COLS["expenses"]),
        "trip_capsule_entries": fetch_all_rows(
            supabase, "trip_capsule_entries", SAFE_SELECT_COLS["trip_capsule_entries"]
        ),
        "user_preferences": fetch_all_rows(
            supabase, "user_preferences", SAFE_SELECT_COLS["user_preferences"]
        ),
        "notifications": fetch_all_rows(
            supabase, "notifications", SAFE_SELECT_COLS["notifications"]
        ),
        "push_subscriptions": fetch_all_rows(
            supabase, "push_subscriptions", SAFE_SELECT_COLS["push_subscriptions"]
        ),
    }


# ---------------------------------------------------------------------------
# Audit & Purge Planning (Pure Logic, 100% Unit-Testable)
# ---------------------------------------------------------------------------
def _find_ryan_test_row(users: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    env_ryan = _get_env_ryan_test_id()
    for u in users:
        uid = str(u.get("id") or "").strip().lower()
        if not uid:
            continue
        if sha256_uid(uid) == RYAN_TEST_UID_SHA256:
            return u
        if env_ryan and uid == env_ryan:
            return u
    return None


def build_purge_plan(
    snapshot: Dict[str, List[Dict[str, Any]]],
    *,
    now: Optional[datetime] = None,
    approved_user_ids: Sequence[str] = APPROVED_PURGE_USER_IDS,
    cooldown_hours: float = SYSTEM_COOLDOWN_HOURS,
) -> Dict[str, Any]:
    """
    Build deterministic purge plan with all guardrails enforced:
    - Hard-protected SHA-256 whitelist (main account + 6-account test pool).
    - Explicit approved 36-char UUID list only for public.users deletions.
    - Guardrail resolution (a): has_external_expenses only aborts if expense is outside approved
      deletion itineraries (allowing #29 daec9523's expense on TEST-SUCCESS 0f2410b7-...).
    - Guardrail resolution (b): exempts [Test] Editor (00002) dangling row on TEST-FULL-FLOW
      (f4a1773d-...) while preserving [Test] Editor account.
    - Checks BOTH itineraries.created_by and itineraries.user_id to guard fk_itineraries_user CASCADE.
    - Empty SYSTEM sample trips strictly require created_by == 'SYSTEM' (protecting created_by IS NULL)
      and age >= cooldown_hours (protecting concurrent seed-sample).
    """
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now_utc - timedelta(hours=cooldown_hours)

    users = snapshot.get("users", [])
    itineraries = snapshot.get("itineraries", [])
    members = snapshot.get("trip_members", [])
    expenses = snapshot.get("expenses", [])
    capsules = snapshot.get("trip_capsule_entries", [])
    pushes = snapshot.get("push_subscriptions", [])
    notifs = snapshot.get("notifications", [])
    prefs = snapshot.get("user_preferences", [])

    users_by_id: Dict[str, Dict[str, Any]] = {
        str(u["id"]).strip().lower(): u for u in users if u.get("id")
    }
    existing_user_ids: Set[str] = set(users_by_id.keys())

    itins_by_id: Dict[str, Dict[str, Any]] = {
        str(t["id"]).strip().lower(): t for t in itineraries if t.get("id")
    }

    members_by_trip: Dict[str, List[Dict[str, Any]]] = {}
    members_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for m in members:
        tid = str(m.get("itinerary_id") or "").strip().lower()
        uid = str(m.get("user_id") or "").strip().lower()
        if tid:
            members_by_trip.setdefault(tid, []).append(m)
        if uid:
            members_by_user.setdefault(uid, []).append(m)

    expenses_by_trip: Dict[str, List[Dict[str, Any]]] = {}
    expenses_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for e in expenses:
        tid = str(e.get("itinerary_id") or "").strip().lower()
        if tid:
            expenses_by_trip.setdefault(tid, []).append(e)
        for col in ("created_by", "payer_id"):
            val = str(e.get(col) or "").strip().lower()
            if val:
                expenses_by_user.setdefault(val, []).append(e)

    capsules_by_trip: Dict[str, List[Dict[str, Any]]] = {}
    capsules_by_author: Dict[str, List[Dict[str, Any]]] = {}
    for c in capsules:
        tid = str(c.get("trip_id") or "").strip().lower()
        aid = str(c.get("author_id") or "").strip().lower()
        if tid:
            capsules_by_trip.setdefault(tid, []).append(c)
        if aid:
            capsules_by_author.setdefault(aid, []).append(c)

    pushes_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for p in pushes:
        uid = str(p.get("user_id") or "").strip().lower()
        if uid:
            pushes_by_user.setdefault(uid, []).append(p)

    # Normalize approved user UUID list and immediately block any hard-protected IDs
    disqualified_users: List[Dict[str, Any]] = []
    candidate_approved_ids: Set[str] = set()
    for raw_uid in approved_user_ids:
        uid = str(raw_uid or "").strip().lower()
        if not is_valid_uuid(uid):
            disqualified_users.append({"user_id": raw_uid, "reason": "invalid_uuid_format"})
            continue
        if is_hard_protected_user(uid):
            disqualified_users.append({"user_id": uid, "reason": "hard_protected_user"})
            continue
        candidate_approved_ids.add(uid)

    # 1. Candidate Approved Non-UUID Test Creator Itineraries (validated jointly in fixed-point loop below)
    candidate_non_uuid_trip_ids: Set[str] = set()
    disqualified_trips: List[Dict[str, Any]] = []
    disqualified_trip_map: Dict[str, str] = {}

    for tid, t in itins_by_id.items():
        cb_raw = t.get("created_by")
        if cb_raw is None:
            continue
        cb = str(cb_raw).strip()
        if cb == "SYSTEM" or is_valid_uuid(cb):
            continue
        if cb not in APPROVED_NON_UUID_CREATORS:
            continue
        candidate_non_uuid_trip_ids.add(tid)

    # 2. Orphan Explorer Members & Their Exclusive SYSTEM Sample Itineraries
    orphan_explorer_members: List[Dict[str, Any]] = []
    orphan_explorer_trips: List[Dict[str, Any]] = []
    orphan_explorer_trip_ids: Set[str] = set()
    orphan_explorer_user_ids: Set[str] = set()

    for m in members:
        m_uid_raw = str(m.get("user_id") or "").strip()
        m_uid = m_uid_raw.lower()
        if not m_uid or m_uid in existing_user_ids or is_hard_protected_user(m_uid):
            continue
        if m_uid_raw in APPROVED_NON_UUID_CREATORS:
            continue
        if (m.get("user_name") or "").strip() != "Explorer":
            continue
        tid = str(m.get("itinerary_id") or "").strip().lower()
        t = itins_by_id.get(tid)
        if not t:
            continue
        if t.get("created_by") != "SYSTEM" or t.get("title") != SAMPLE_TRIP_TITLE:
            continue
        if t.get("user_id") is not None:
            continue
        if len(members_by_trip.get(tid, [])) != 1:
            continue
        if expenses_by_trip.get(tid) or capsules_by_trip.get(tid):
            continue
        created_dt = parse_iso_timestamp(t.get("created_at"))
        if created_dt is None or created_dt > cutoff:
            disqualified_trips.append(
                {"itinerary_id": tid, "title": t.get("title"), "reason": "system_cooldown_active"}
            )
            continue

        orphan_explorer_members.append(m)
        orphan_explorer_trips.append(t)
        orphan_explorer_trip_ids.add(tid)
        orphan_explorer_user_ids.add(m_uid_raw)

    # 3. Empty SYSTEM Sample Itineraries (strictly created_by == 'SYSTEM' + >= 1h cooldown)
    empty_system_trips: List[Dict[str, Any]] = []
    empty_system_trip_ids: Set[str] = set()
    skipped_null_creator_trips: List[Dict[str, Any]] = []
    skipped_recent_system_trips: List[Dict[str, Any]] = []

    for tid, t in itins_by_id.items():
        if t.get("created_by") is None:
            skipped_null_creator_trips.append(t)
            continue
        if t.get("created_by") != "SYSTEM":
            continue
        if tid in orphan_explorer_trip_ids:
            continue
        if len(members_by_trip.get(tid, [])) != 0:
            continue
        if t.get("title") != SAMPLE_TRIP_TITLE or t.get("user_id") is not None:
            continue
        if expenses_by_trip.get(tid) or capsules_by_trip.get(tid):
            continue
        created_dt = parse_iso_timestamp(t.get("created_at"))
        if created_dt is None or created_dt > cutoff:
            skipped_recent_system_trips.append(t)
            continue
        empty_system_trips.append(t)
        empty_system_trip_ids.add(tid)

    # 4. Orphan Push Subscriptions (no matching public.users row)
    orphan_push_subs: List[Dict[str, Any]] = []
    orphan_push_user_ids: Set[str] = set()
    for p in pushes:
        p_uid_raw = str(p.get("user_id") or "").strip()
        p_uid = p_uid_raw.lower()
        if not p_uid or p_uid in existing_user_ids or is_hard_protected_user(p_uid):
            continue
        orphan_push_subs.append(p)
        orphan_push_user_ids.add(p_uid_raw)

    # 5. Joint Fixed-Point Qualification of Non-UUID Trips & Approved Target Users
    # Guarantees monotonic convergence: if any user is disqualified, any non-UUID trip referencing
    # that user (user_id / trip_members / expenses / capsules) is disqualified too, and any other
    # approved user whose expense depended on that trip is disqualified on the next pass.
    active_approved = {uid for uid in candidate_approved_ids if uid in users_by_id}
    active_non_uuid_trip_ids = set(candidate_non_uuid_trip_ids)
    disqualified_map: Dict[str, str] = {}

    while True:
        newly_disqualified_trips: Dict[str, str] = {}
        for tid in sorted(active_non_uuid_trip_ids):
            t = itins_by_id[tid]
            trip_owner_uid = str(t.get("user_id") or "").strip().lower()
            if trip_owner_uid and (
                is_hard_protected_user(trip_owner_uid) or trip_owner_uid not in active_approved
            ):
                newly_disqualified_trips[tid] = "non_target_user_id_fk"
                continue

            trip_reason: Optional[str] = None
            for m in members_by_trip.get(tid, []):
                m_uid_raw = str(m.get("user_id") or "").strip()
                m_uid = m_uid_raw.lower()
                if (tid, m_uid) in EXEMPT_ORPHAN_TRIP_MEMBERSHIPS:
                    continue
                if m_uid_raw in APPROVED_NON_UUID_CREATORS or m_uid in active_approved:
                    continue
                trip_reason = "non_exempt_member_present"
                break
            if trip_reason:
                newly_disqualified_trips[tid] = trip_reason
                continue

            for e in expenses_by_trip.get(tid, []):
                for col in ("created_by", "payer_id"):
                    val_raw = str(e.get(col) or "").strip()
                    val = val_raw.lower()
                    if not val:
                        continue
                    if is_hard_protected_user(val) or (
                        val not in active_approved and val_raw not in APPROVED_NON_UUID_CREATORS
                    ):
                        trip_reason = "non_target_expense_on_trip"
                        break
                if trip_reason:
                    break
            if trip_reason:
                newly_disqualified_trips[tid] = trip_reason
                continue

            for c in capsules_by_trip.get(tid, []):
                aid = str(c.get("author_id") or "").strip().lower()
                if aid and (is_hard_protected_user(aid) or aid not in active_approved):
                    trip_reason = "non_target_capsule_on_trip"
                    break
            if trip_reason:
                newly_disqualified_trips[tid] = trip_reason
                continue

        for tid, rsn in newly_disqualified_trips.items():
            active_non_uuid_trip_ids.discard(tid)
            disqualified_trip_map[tid] = rsn

        newly_disqualified: Dict[str, str] = {}
        for uid in sorted(active_approved):
            if is_hard_protected_user(uid):
                newly_disqualified[uid] = "hard_protected_user"
                continue

            # Check owned itineraries via BOTH created_by AND user_id (fk_itineraries_user ON DELETE CASCADE)
            owned_trips = [
                t
                for t in itineraries
                if str(t.get("created_by") or "").strip().lower() == uid
                or str(t.get("user_id") or "").strip().lower() == uid
            ]
            owned_trip_ids = {str(t["id"]).strip().lower() for t in owned_trips if t.get("id")}

            reason: Optional[str] = None
            for t in owned_trips:
                tid = str(t["id"]).strip().lower()
                t_uid = str(t.get("user_id") or "").strip().lower()
                t_cb_raw_val = t.get("created_by")
                if t_cb_raw_val is None:
                    reason = "owned_trip_null_creator"
                    break
                t_cb_raw = str(t_cb_raw_val).strip()
                t_cb_lower = t_cb_raw.lower()
                if t_uid and t_uid not in active_approved:
                    reason = "fk_itineraries_user_non_target"
                    break
                if t_cb_raw != "SYSTEM" and t_cb_lower not in active_approved:
                    reason = "owned_trip_creator_non_target"
                    break
                for m in members_by_trip.get(tid, []):
                    m_uid = str(m.get("user_id") or "").strip().lower()
                    if m_uid not in active_approved and (tid, m_uid) not in EXEMPT_ORPHAN_TRIP_MEMBERSHIPS:
                        reason = "shared_owned_itinerary"
                        break
                if reason:
                    break
            if reason:
                newly_disqualified[uid] = reason
                continue

            # Check itineraries where user is a member
            user_member_rows = members_by_user.get(uid, [])
            exclusive_system_trip_ids: Set[str] = set()
            for m in user_member_rows:
                tid = str(m.get("itinerary_id") or "").strip().lower()
                if not tid or tid in owned_trip_ids or tid in active_non_uuid_trip_ids:
                    continue
                t = itins_by_id.get(tid)
                if not t:
                    continue
                t_cb = t.get("created_by")
                t_uid = str(t.get("user_id") or "").strip().lower()
                if t_uid and t_uid not in active_approved:
                    reason = "member_trip_user_id_non_target"
                    break
                trip_member_uids = {
                    str(tm.get("user_id") or "").strip().lower()
                    for tm in members_by_trip.get(tid, [])
                }
                if not trip_member_uids.issubset(active_approved):
                    reason = "shares_itinerary_with_non_target_user"
                    break
                if t_cb == "SYSTEM":
                    if expenses_by_trip.get(tid) or capsules_by_trip.get(tid):
                        reason = "system_trip_has_activity"
                        break
                    exclusive_system_trip_ids.add(tid)
                else:
                    t_cb_lower = str(t_cb or "").strip().lower()
                    if t_cb_lower not in active_approved:
                        reason = "member_of_non_target_itinerary"
                        break
            if reason:
                newly_disqualified[uid] = reason
                continue

            # Guardrail (a): has_external_expenses aborts only when expense does NOT belong to approved deletion trips
            user_related_expenses = list(expenses_by_user.get(uid, []))
            for tid in owned_trip_ids | exclusive_system_trip_ids:
                user_related_expenses.extend(expenses_by_trip.get(tid, []))
            for e in user_related_expenses:
                exp_tid = str(e.get("itinerary_id") or "").strip().lower()
                if exp_tid not in active_non_uuid_trip_ids:
                    reason = "has_external_expenses"
                    break
            if reason:
                newly_disqualified[uid] = reason
                continue

            # Capsules check
            user_related_capsules = list(capsules_by_author.get(uid, []))
            for tid in owned_trip_ids | exclusive_system_trip_ids:
                user_related_capsules.extend(capsules_by_trip.get(tid, []))
            for c in user_related_capsules:
                cap_tid = str(c.get("trip_id") or "").strip().lower()
                if cap_tid not in active_non_uuid_trip_ids:
                    reason = "has_capsule_entries"
                    break
            if reason:
                newly_disqualified[uid] = reason
                continue

            # Push subscriptions check for active public.users rows
            if pushes_by_user.get(uid):
                newly_disqualified[uid] = "has_push_subscriptions"
                continue

        if not newly_disqualified and not newly_disqualified_trips:
            break
        for uid, rsn in newly_disqualified.items():
            active_approved.discard(uid)
            disqualified_map[uid] = rsn

    for tid, rsn in sorted(disqualified_trip_map.items()):
        disqualified_trips.append(
            {"itinerary_id": tid, "title": itins_by_id.get(tid, {}).get("title"), "reason": rsn}
        )

    non_uuid_trip_ids: Set[str] = set(active_non_uuid_trip_ids)
    non_uuid_trips: List[Dict[str, Any]] = [itins_by_id[tid] for tid in sorted(non_uuid_trip_ids)]
    non_uuid_creators_matched: Set[str] = {
        str(t.get("created_by") or "").strip() for t in non_uuid_trips if t.get("created_by")
    }
    exempt_member_rows: List[Dict[str, Any]] = []
    for tid in sorted(non_uuid_trip_ids):
        for m in members_by_trip.get(tid, []):
            m_uid = str(m.get("user_id") or "").strip().lower()
            if (tid, m_uid) in EXEMPT_ORPHAN_TRIP_MEMBERSHIPS:
                exempt_member_rows.append(m)

    for uid, rsn in sorted(disqualified_map.items()):
        disqualified_users.append(
            {"user_id": uid, "name": users_by_id.get(uid, {}).get("name"), "reason": rsn}
        )

    qualified_user_ids = sorted(active_approved)
    qualified_users = [users_by_id[uid] for uid in qualified_user_ids]

    # Collect all itineraries owned by or exclusively assigned (SYSTEM) to qualified users
    user_owned_trip_ids: Set[str] = set()
    user_exclusive_system_trip_ids: Set[str] = set()
    for uid in qualified_user_ids:
        for t in itineraries:
            tid = str(t.get("id") or "").strip().lower()
            if not tid:
                continue
            if (
                str(t.get("created_by") or "").strip().lower() == uid
                or str(t.get("user_id") or "").strip().lower() == uid
            ):
                user_owned_trip_ids.add(tid)
        for m in members_by_user.get(uid, []):
            tid = str(m.get("itinerary_id") or "").strip().lower()
            t = itins_by_id.get(tid)
            if t and t.get("created_by") == "SYSTEM":
                user_exclusive_system_trip_ids.add(tid)

    all_target_trip_ids = sorted(
        non_uuid_trip_ids
        | orphan_explorer_trip_ids
        | empty_system_trip_ids
        | user_owned_trip_ids
        | user_exclusive_system_trip_ids
    )
    all_target_trip_set = set(all_target_trip_ids)

    # Multi-table target subsets
    target_expenses = [
        e
        for e in expenses
        if str(e.get("itinerary_id") or "").strip().lower() in all_target_trip_set
        or str(e.get("created_by") or "").strip().lower() in active_approved
        or str(e.get("payer_id") or "").strip().lower() in active_approved
    ]
    target_capsules = [
        c
        for c in capsules
        if str(c.get("trip_id") or "").strip().lower() in all_target_trip_set
        or str(c.get("author_id") or "").strip().lower() in active_approved
    ]
    exempt_member_id_set = {str(m["id"]).strip().lower() for m in exempt_member_rows if m.get("id")}
    orphan_member_id_set = {
        str(m["id"]).strip().lower() for m in orphan_explorer_members if m.get("id")
    }
    target_members = [
        m
        for m in members
        if str(m.get("id") or "").strip().lower() in (exempt_member_id_set | orphan_member_id_set)
        or str(m.get("itinerary_id") or "").strip().lower() in all_target_trip_set
        or str(m.get("user_id") or "").strip().lower() in active_approved
    ]

    # Identify any orphan IDs still referenced by retained (non-target) trips/members/expenses/capsules
    retained_referenced_uids: Set[str] = set()
    for tid, t in itins_by_id.items():
        if tid in all_target_trip_set:
            continue
        for col in ("created_by", "user_id"):
            v = str(t.get(col) or "").strip().lower()
            if v:
                retained_referenced_uids.add(v)
    for m in members:
        mid = str(m.get("id") or "").strip().lower()
        tid = str(m.get("itinerary_id") or "").strip().lower()
        uid = str(m.get("user_id") or "").strip().lower()
        if mid in (exempt_member_id_set | orphan_member_id_set) or tid in all_target_trip_set or uid in active_approved:
            continue
        if uid:
            retained_referenced_uids.add(uid)
    for e in expenses:
        tid = str(e.get("itinerary_id") or "").strip().lower()
        if tid in all_target_trip_set:
            continue
        for col in ("created_by", "payer_id"):
            v = str(e.get(col) or "").strip().lower()
            if v:
                retained_referenced_uids.add(v)
    for c in capsules:
        tid = str(c.get("trip_id") or "").strip().lower()
        if tid in all_target_trip_set:
            continue
        aid = str(c.get("author_id") or "").strip().lower()
        if aid:
            retained_referenced_uids.add(aid)

    safe_orphan_explorer_user_ids = [
        u for u in sorted(orphan_explorer_user_ids) if u.lower() not in retained_referenced_uids
    ]
    safe_orphan_push_user_ids = [
        u for u in sorted(orphan_push_user_ids) if u.lower() not in retained_referenced_uids
    ]

    # Targeted notification user IDs: qualified users + non-UUID creators (test-uuid) + isolated orphan Explorers + isolated orphan push users (c4f87a37)
    target_notif_user_ids = unique_strings(
        [
            *qualified_user_ids,
            *sorted(non_uuid_creators_matched),
            *safe_orphan_explorer_user_ids,
            *safe_orphan_push_user_ids,
        ]
    )
    target_notif_uid_lower = {u.lower() for u in target_notif_user_ids}
    target_notifications = [
        n
        for n in notifs
        if str(n.get("user_id") or "").strip().lower() in target_notif_uid_lower
    ]

    target_pref_user_ids = uuid_only(
        [*qualified_user_ids, *safe_orphan_explorer_user_ids, *safe_orphan_push_user_ids]
    )
    target_pref_uid_set = set(target_pref_user_ids)
    target_preferences = [
        pr
        for pr in prefs
        if str(pr.get("user_id") or "").strip().lower() in target_pref_uid_set
    ]

    # Collect Cloudinary asset URLs from users.avatar_url and trip_capsule_entries.photo_url
    cloudinary_urls: Set[str] = set()
    for u in qualified_users:
        av = u.get("avatar_url")
        if isinstance(av, str) and extract_cloudinary_asset(av.strip()) is not None:
            cloudinary_urls.add(av.strip())
    for c in target_capsules:
        pu = c.get("photo_url")
        if isinstance(pu, str) and extract_cloudinary_asset(pu.strip()) is not None:
            cloudinary_urls.add(pu.strip())

    # Unapproved historical orphan notifications (audit visibility only, never deleted by purge)
    unapproved_orphan_notifs_count = sum(
        1
        for n in notifs
        if str(n.get("user_id") or "").strip().lower() not in existing_user_ids
        and str(n.get("user_id") or "").strip().lower() not in target_notif_uid_lower
    )

    return {
        "generated_at": now_utc.isoformat(),
        "qualified_users": qualified_users,
        "qualified_user_ids": qualified_user_ids,
        "disqualified_users": disqualified_users,
        "non_uuid_trips": non_uuid_trips,
        "non_uuid_trip_ids": sorted(non_uuid_trip_ids),
        "non_uuid_creators": sorted(non_uuid_creators_matched),
        "exempt_member_rows": exempt_member_rows,
        "orphan_explorer_members": orphan_explorer_members,
        "orphan_explorer_trips": orphan_explorer_trips,
        "orphan_explorer_trip_ids": sorted(orphan_explorer_trip_ids),
        "orphan_explorer_user_ids": sorted(orphan_explorer_user_ids),
        "empty_system_trips": empty_system_trips,
        "empty_system_trip_ids": sorted(empty_system_trip_ids),
        "user_owned_trip_ids": sorted(user_owned_trip_ids),
        "user_exclusive_system_trip_ids": sorted(user_exclusive_system_trip_ids),
        "all_target_trip_ids": all_target_trip_ids,
        "all_target_trips": [itins_by_id[tid] for tid in all_target_trip_ids if tid in itins_by_id],
        "target_expenses": target_expenses,
        "target_capsules": target_capsules,
        "target_members": target_members,
        "target_notifications": target_notifications,
        "target_notif_user_ids": target_notif_user_ids,
        "target_preferences": target_preferences,
        "target_pref_user_ids": target_pref_user_ids,
        "orphan_push_subs": orphan_push_subs,
        "orphan_push_user_ids": sorted(orphan_push_user_ids),
        "cloudinary_urls": sorted(cloudinary_urls),
        "disqualified_trips": disqualified_trips,
        "skipped_null_creator_trips_count": len(skipped_null_creator_trips),
        "skipped_recent_system_trips_count": len(skipped_recent_system_trips),
        "unapproved_orphan_notifs_count": unapproved_orphan_notifs_count,
    }


def build_audit_report(
    snapshot: Dict[str, List[Dict[str, Any]]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Read-only health check of the 6-account test pool, approved purge candidates, and drift."""
    users = snapshot.get("users", [])
    users_by_id = {str(u["id"]).strip().lower(): u for u in users if u.get("id")}
    approved_set = {uid.lower() for uid in APPROVED_PURGE_USER_IDS}

    pool_status: List[Dict[str, Any]] = []
    for role in ("OWNER", "EDITOR", "VIEWER", "CAPSULE", "STRANGER"):
        meta = TEST_USERS[role]
        uid = meta["id"].lower()
        row = users_by_id.get(uid)
        expected_mode = meta["auth_mode"]
        has_key = bool(row and row.get("recovery_key_id"))
        actual_mode = "missing" if row is None else ("modern" if has_key else "legacy")
        pool_status.append(
            {
                "role": role,
                "id_prefix": uid[:8] + "..." + uid[-5:],
                "exists": row is not None,
                "name": row.get("name") if row else None,
                "expected_auth_mode": expected_mode,
                "actual_auth_mode": actual_mode,
                "credential_version": row.get("credential_version") if row else None,
                "compliant": actual_mode == expected_mode,
            }
        )

    ryan_test_row = _find_ryan_test_row(users)
    rt_has_key = bool(ryan_test_row and ryan_test_row.get("recovery_key_id"))
    rt_actual = "missing" if ryan_test_row is None else ("modern" if rt_has_key else "legacy")
    pool_status.append(
        {
            "role": "RYAN_TEST",
            "id_prefix": "sha256:" + RYAN_TEST_UID_SHA256[:12],
            "exists": ryan_test_row is not None,
            "name": ryan_test_row.get("name") if ryan_test_row else None,
            "expected_auth_mode": "modern",
            "actual_auth_mode": rt_actual,
            "credential_version": ryan_test_row.get("credential_version") if ryan_test_row else None,
            "compliant": rt_actual == "modern",
        }
    )

    main_row = next((u for u in users if sha256_uid(u.get("id", "")) == MAIN_USER_UID_SHA256), None)

    plan = build_purge_plan(snapshot, now=now)

    # Detect any NEW suspect test accounts not in the approved list and not protected
    new_suspect_accounts: List[Dict[str, Any]] = []
    for u in users:
        uid = str(u.get("id") or "").strip().lower()
        if not uid or uid in approved_set or is_hard_protected_user(uid):
            continue
        name = str(u.get("name") or "").strip()
        if name and SUSPECT_TEST_NAME_RE.search(name):
            new_suspect_accounts.append(
                {
                    "id_prefix": uid[:8],
                    "name": name,
                    "created_at": u.get("created_at"),
                }
            )

    return {
        "total_users": len(users),
        "total_itineraries": len(snapshot.get("itineraries", [])),
        "total_trip_members": len(snapshot.get("trip_members", [])),
        "total_expenses": len(snapshot.get("expenses", [])),
        "total_push_subscriptions": len(snapshot.get("push_subscriptions", [])),
        "total_notifications": len(snapshot.get("notifications", [])),
        "main_account_present": main_row is not None,
        "pool_status": pool_status,
        "purge_summary": {
            "qualified_users": len(plan["qualified_user_ids"]),
            "disqualified_users": len(plan["disqualified_users"]),
            "non_uuid_trips": len(plan["non_uuid_trip_ids"]),
            "orphan_explorer_pairs": len(plan["orphan_explorer_members"]),
            "empty_system_trips": len(plan["empty_system_trip_ids"]),
            "all_target_trips": len(plan["all_target_trip_ids"]),
            "exempt_member_rows": len(plan["exempt_member_rows"]),
            "orphan_push_subs": len(plan["orphan_push_subs"]),
            "target_notifications": len(plan["target_notifications"]),
            "unapproved_orphan_notifs": plan["unapproved_orphan_notifs_count"],
            "cloudinary_assets": len(plan["cloudinary_urls"]),
            "protected_null_creator_trips": plan["skipped_null_creator_trips_count"],
            "cooldown_skipped_system_trips": plan["skipped_recent_system_trips_count"],
        },
        "new_suspect_accounts": new_suspect_accounts,
    }


# ---------------------------------------------------------------------------
# Redacted Physical Backup
# ---------------------------------------------------------------------------
def build_redacted_backup_payload(
    plan: Dict[str, Any],
    itinerary_items: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    raw_payload = {
        "timestamp": plan["generated_at"],
        "summary": {
            "users": len(plan["qualified_users"]),
            "itineraries": len(plan["all_target_trips"]),
            "itinerary_items": len(itinerary_items),
            "trip_members": len(plan["target_members"]),
            "expenses": len(plan["target_expenses"]),
            "trip_capsule_entries": len(plan["target_capsules"]),
            "user_preferences": len(plan["target_preferences"]),
            "notifications": len(plan["target_notifications"]),
            "push_subscriptions": len(plan["orphan_push_subs"]),
            "cloudinary_assets": len(plan["cloudinary_urls"]),
        },
        "users": plan["qualified_users"],
        "itineraries": plan["all_target_trips"],
        "itinerary_items": list(itinerary_items),
        "trip_members": plan["target_members"],
        "expenses": plan["target_expenses"],
        "trip_capsule_entries": plan["target_capsules"],
        "user_preferences": plan["target_preferences"],
        "notifications": plan["target_notifications"],
        "push_subscriptions": plan["orphan_push_subs"],
        "cloudinary_urls": plan["cloudinary_urls"],
    }
    return strip_sensitive_fields(raw_payload)


def write_redacted_backup(
    payload: Dict[str, Any],
    backup_path: str | Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> Tuple[Path, str]:
    """Validate path containment inside docs/migrations/backups/, verify gitignore, and write redacted JSON."""
    safe_path = resolve_safe_backup_path(backup_path, repo_root=repo_root)
    assert_git_ignored(safe_path, "Backup file", repo_root=repo_root)

    redacted = strip_sensitive_fields(payload)
    serialized = json.dumps(redacted, indent=2, ensure_ascii=False)
    for forbidden in SENSITIVE_BACKUP_FIELDS:
        if f'"{forbidden}"' in serialized:
            raise RuntimeError(f"Sensitive field '{forbidden}' leaked into redacted backup payload!")

    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(serialized, encoding="utf-8")
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return safe_path, digest


# ---------------------------------------------------------------------------
# Cloudinary Explicit Destroy (Fail-Loud, Never Swallow 401)
# ---------------------------------------------------------------------------
def _preflight_cloudinary_targets(
    urls: Iterable[str],
) -> Tuple[Dict[Tuple[str, str], Optional[str]], Tuple[str, str, str]]:
    """
    Parse target Cloudinary URLs and fail-closed on missing credentials or cloud mismatch
    BEFORE any irreversible database deletion occurs.
    """
    targets: Dict[Tuple[str, str], Optional[str]] = {}
    for raw_url in urls:
        asset = extract_cloudinary_asset(raw_url)
        if asset is None:
            continue
        asset_cloud, resource_type, public_id = asset
        targets.setdefault((resource_type, public_id), asset_cloud)

    if not targets:
        return {}, ("", "", "")

    cloud_name, api_key, api_secret = get_cloudinary_config()
    if not (cloud_name and api_key and api_secret):
        raise RuntimeError(
            "Cloudinary credentials (CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET) are required "
            f"to destroy {len(targets)} asset(s)."
        )
    for (_, public_id), asset_cloud in targets.items():
        if asset_cloud and asset_cloud != cloud_name:
            raise RuntimeError(
                f"Cloudinary cloud mismatch for '{public_id}': url cloud '{asset_cloud}' != '{cloud_name}'"
            )
    return targets, (cloud_name, api_key, api_secret)


def destroy_cloudinary_assets_strict(
    urls: Iterable[str],
    *,
    http_client: Optional[httpx.Client] = None,
    timeout: float = 15.0,
) -> Dict[str, str]:
    """
    Explicitly call Cloudinary destroy API and assert HTTP 200 AND result in {'ok', 'not found'}.
    Never silently swallows HTTP 401 or unexpected error results.
    """
    targets, (cloud_name, api_key, api_secret) = _preflight_cloudinary_targets(urls)
    if not targets:
        return {}

    results: Dict[str, str] = {}
    own_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout)
    try:
        for (resource_type, public_id), _ in targets.items():
            timestamp = int(time.time())
            sig_payload = f"invalidate=true&public_id={public_id}&timestamp={timestamp}{api_secret}"
            signature = hashlib.sha1(sig_payload.encode("utf-8")).hexdigest()
            endpoint = (
                f"https://api.cloudinary.com/v1_1/{quote(cloud_name, safe='')}/{resource_type}/destroy"
            )
            resp = client.post(
                endpoint,
                data={
                    "public_id": public_id,
                    "timestamp": str(timestamp),
                    "api_key": api_key,
                    "invalidate": "true",
                    "signature": signature,
                },
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Cloudinary destroy failed for '{public_id}': HTTP {resp.status_code} ({resp.text[:200]})"
                )
            try:
                payload = resp.json() if resp.content else {}
            except ValueError as err:
                raise RuntimeError(
                    f"Cloudinary destroy returned invalid JSON for '{public_id}': {err}"
                ) from err
            result = payload.get("result") if isinstance(payload, dict) else None
            if result not in {"ok", "not found"}:
                raise RuntimeError(
                    f"Cloudinary destroy unexpected result for '{public_id}': {result!r}"
                )
            results[public_id] = str(result)
    finally:
        if own_client:
            client.close()

    return results


# ---------------------------------------------------------------------------
# Purge Execution (FK-Ordered, UUID-Safe, Trigger-Throttled)
# ---------------------------------------------------------------------------
def _delete_in_chunks(
    supabase: Client,
    table: str,
    column: str,
    values: Sequence[str],
    *,
    chunk_size: int = CHUNK_SIZE,
    sleep_sec: float = 0.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> List[Dict[str, Any]]:
    deleted_rows: List[Dict[str, Any]] = []
    deduped = unique_strings(values)
    for i in range(0, len(deduped), chunk_size):
        chunk = deduped[i : i + chunk_size]
        res = supabase.table(table).delete().in_(column, chunk).execute()
        data = getattr(res, "data", None)
        if isinstance(data, list):
            deleted_rows.extend(data)
        if sleep_sec > 0:
            sleep_fn(sleep_sec)
    return deleted_rows


def execute_purge(
    supabase: Client,
    plan: Dict[str, Any],
    itinerary_items: Sequence[Dict[str, Any]],
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    http_client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """
    Execute FK-ordered chunked purge with row-level trigger throttling:
    1. expenses (by itinerary_id, created_by, payer_id — all UUID filtered)
    2. itinerary_items (by id, batch=25 + sleep 0.3s)
    3. trip_capsule_entries (by trip_id, author_id — UUID filtered; collect photo_url)
    4. trip_members (by explicit row id, itinerary_id, user_id)
    5. itineraries (by id, batch=25 + sleep 0.3s)
    6. user_preferences (by user_id — UUID filtered)
    7. notifications (by user_id — TEXT, includes test-uuid & c4f87a37)
    8. push_subscriptions (by id & user_id)
    9. users (by id — UUID filtered + final hard-protected guard; collect avatar_url)
    10. Cloudinary destroy (strict HTTP 200 + result in {"ok", "not found"})
    """
    target_user_ids = uuid_only(plan["qualified_user_ids"])
    for uid in target_user_ids:
        if is_hard_protected_user(uid):
            raise RuntimeError(f"🚨 [ABORT] Hard-protected user {sha256_uid(uid)[:12]} reached execute_purge!")

    cloudinary_urls: Set[str] = set(plan.get("cloudinary_urls", []))
    # Preflight Cloudinary credentials & cloud match BEFORE mutating a single DB row
    _preflight_cloudinary_targets(cloudinary_urls)

    target_trip_ids = uuid_only(plan["all_target_trip_ids"])
    target_trip_set = set(target_trip_ids)
    target_item_ids = uuid_only(
        item.get("id")
        for item in itinerary_items
        if str(item.get("itinerary_id") or "").strip().lower() in target_trip_set
    )
    explicit_member_ids = uuid_only(
        [
            *(m.get("id") for m in plan.get("exempt_member_rows", [])),
            *(m.get("id") for m in plan.get("orphan_explorer_members", [])),
        ]
    )
    target_pref_user_ids = uuid_only(plan.get("target_pref_user_ids", []))
    target_notif_user_ids = unique_strings(plan.get("target_notif_user_ids", []))
    orphan_push_sub_ids = uuid_only(p.get("id") for p in plan.get("orphan_push_subs", []))

    counts: Dict[str, int] = {}

    # 1. expenses (UUID columns)
    exp_rows: List[Dict[str, Any]] = []
    exp_rows.extend(_delete_in_chunks(supabase, "expenses", "itinerary_id", target_trip_ids))
    exp_rows.extend(_delete_in_chunks(supabase, "expenses", "created_by", target_user_ids))
    exp_rows.extend(_delete_in_chunks(supabase, "expenses", "payer_id", target_user_ids))
    counts["expenses"] = len(exp_rows)

    # 2. itinerary_items (by id, TRIGGER_BATCH_SIZE=25 + 0.3s sleep)
    item_rows = _delete_in_chunks(
        supabase,
        "itinerary_items",
        "id",
        target_item_ids,
        chunk_size=TRIGGER_BATCH_SIZE,
        sleep_sec=TRIGGER_BATCH_SLEEP_SEC,
        sleep_fn=sleep_fn,
    )
    counts["itinerary_items"] = len(item_rows)

    # 3. trip_capsule_entries (UUID columns)
    cap_rows: List[Dict[str, Any]] = []
    cap_rows.extend(_delete_in_chunks(supabase, "trip_capsule_entries", "trip_id", target_trip_ids))
    cap_rows.extend(_delete_in_chunks(supabase, "trip_capsule_entries", "author_id", target_user_ids))
    for row in cap_rows:
        pu = row.get("photo_url")
        if isinstance(pu, str) and extract_cloudinary_asset(pu.strip()) is not None:
            cloudinary_urls.add(pu.strip())
    counts["trip_capsule_entries"] = len(cap_rows)

    # 4. trip_members (UUID id & itinerary_id; TEXT user_id strictly scoped to qualified target_user_ids
    #    so non-target/disqualified trips referencing non_uuid_creators or orphan users are never touched)
    mem_rows: List[Dict[str, Any]] = []
    mem_rows.extend(_delete_in_chunks(supabase, "trip_members", "id", explicit_member_ids))
    mem_rows.extend(_delete_in_chunks(supabase, "trip_members", "itinerary_id", target_trip_ids))
    mem_rows.extend(_delete_in_chunks(supabase, "trip_members", "user_id", target_user_ids))
    counts["trip_members"] = len(mem_rows)

    # 5. itineraries (by id, TRIGGER_BATCH_SIZE=25 + 0.3s sleep)
    itin_rows = _delete_in_chunks(
        supabase,
        "itineraries",
        "id",
        target_trip_ids,
        chunk_size=TRIGGER_BATCH_SIZE,
        sleep_sec=TRIGGER_BATCH_SLEEP_SEC,
        sleep_fn=sleep_fn,
    )
    counts["itineraries"] = len(itin_rows)

    # 6. user_preferences (UUID user_id)
    pref_rows = _delete_in_chunks(supabase, "user_preferences", "user_id", target_pref_user_ids)
    counts["user_preferences"] = len(pref_rows)

    # 7. notifications (TEXT user_id — covers target users + test-uuid + c4f87a37)
    notif_rows = _delete_in_chunks(supabase, "notifications", "user_id", target_notif_user_ids)
    counts["notifications"] = len(notif_rows)

    # 8. push_subscriptions (UUID id for approved orphans + TEXT user_id for qualified target users)
    push_rows: List[Dict[str, Any]] = []
    push_rows.extend(_delete_in_chunks(supabase, "push_subscriptions", "id", orphan_push_sub_ids))
    push_rows.extend(_delete_in_chunks(supabase, "push_subscriptions", "user_id", target_user_ids))
    counts["push_subscriptions"] = len(push_rows)

    # 9. users (UUID id)
    user_rows = _delete_in_chunks(supabase, "users", "id", target_user_ids)
    for row in user_rows:
        av = row.get("avatar_url")
        if isinstance(av, str) and extract_cloudinary_asset(av.strip()) is not None:
            cloudinary_urls.add(av.strip())
    counts["users"] = len(user_rows)

    # 10. Explicit Cloudinary destroy verification
    cloudinary_results = destroy_cloudinary_assets_strict(cloudinary_urls, http_client=http_client)
    counts["cloudinary_assets"] = len(cloudinary_results)

    return {
        "counts": counts,
        "cloudinary_results": cloudinary_results,
    }


# ---------------------------------------------------------------------------
# Atomic Env Merge Writer & Pool Upgrade Flow
# ---------------------------------------------------------------------------
def parse_env_file(path: Path) -> Tuple[List[str], Dict[str, str]]:
    """Parse existing .env file while preserving order and existing key/value pairs."""
    if not path.exists():
        return [], {}
    order: List[str] = []
    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        if key:
            if key not in values:
                order.append(key)
            values[key] = v.strip()
    return order, values


def atomic_merge_write_env(
    env_out: Path,
    updates: Dict[str, str],
    *,
    repo_root: Path = REPO_ROOT,
) -> Path:
    """
    Atomically read-merge-write secrets to same-directory temp file (.env.test-pool.tmp.local),
    fsync, and os.replace into env_out. Cleans up temp file in finally on any error.
    Enforces bare `git check-ignore -q` on BOTH final file and temp file.
    """
    resolved_out = env_out if env_out.is_absolute() else (repo_root / env_out)
    resolved_out = resolved_out.resolve()
    tmp_path = derive_atomic_tmp_path(resolved_out)

    assert_git_ignored(resolved_out, "Secret env file", repo_root=repo_root)
    assert_git_ignored(tmp_path, "Atomic temp env file", repo_root=repo_root)

    existing_order, merged = parse_env_file(resolved_out)
    for k, v in updates.items():
        if k not in merged:
            existing_order.append(k)
        merged[k] = v

    lines = [
        "# Tabidachi Fixed 6-Account Test Pool Credentials (LOCAL ONLY - GITIGNORED)",
        f"# Last updated (UTC): {datetime.now(timezone.utc).isoformat()}",
    ]
    for k in existing_order:
        lines.append(f"{k}={merged[k]}")
    content = "\n".join(lines) + "\n"

    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    replaced = False
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(3):
            try:
                os.replace(tmp_path, resolved_out)
                replaced = True
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.05)
    finally:
        if not replaced and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return resolved_out


def inspect_pool_upgrade_preflight(
    supabase: Client,
    *,
    target_roles: Sequence[Tuple[str, str]] = UPGRADE_POOL_ROLES,
) -> Dict[str, Any]:
    """
    Verify 00001/00002/00004/00005 exist & inspect recovery_key_id; verify VIEWER (00003) stays Legacy.
    Hard-skips VIEWER (00003), RYAN_TEST (by SHA-256 / env), and MAIN account even if passed in target_roles.
    """
    query_ids = unique_strings([*STATIC_ROLE_TEST_USER_IDS, *(uid for _, uid in target_roles)])
    rows = fetch_rows_by_in_chunks(
        supabase,
        "users",
        "id, name, recovery_key_id, credential_version",
        "id",
        uuid_only(query_ids),
    )
    by_id = {str(r["id"]).strip().lower(): r for r in rows if r.get("id")}

    viewer_row = by_id.get(TEST_USER_VIEWER_ID.lower())
    if viewer_row is None:
        raise RuntimeError(f"Legacy-pinned VIEWER ({TEST_USER_VIEWER_ID}) is missing from public.users!")
    if viewer_row.get("recovery_key_id") is not None:
        raise RuntimeError(
            f"Legacy-pinned VIEWER ({TEST_USER_VIEWER_ID}) already has recovery_key_id set — invariant violated!"
        )

    env_ryan = _get_env_ryan_test_id()

    to_upgrade: List[Tuple[str, str]] = []
    already_upgraded: List[Tuple[str, str]] = []
    missing: List[Tuple[str, str]] = []
    hard_skipped: List[str] = ["VIEWER", "RYAN_TEST"]

    for role, uid in target_roles:
        clean_uid = str(uid or "").strip().lower()
        digest = sha256_uid(clean_uid)
        if (
            clean_uid in LEGACY_PINNED_TEST_IDS
            or clean_uid == SYNTHETIC_RYAN_TEST_ID.lower()
            or (env_ryan and clean_uid == env_ryan)
            or digest in {RYAN_TEST_UID_SHA256, MAIN_USER_UID_SHA256}
        ):
            if role not in hard_skipped:
                hard_skipped.append(role)
            continue
        row = by_id.get(clean_uid)
        if row is None:
            missing.append((role, clean_uid))
        elif row.get("recovery_key_id") is None:
            to_upgrade.append((role, clean_uid))
        else:
            already_upgraded.append((role, clean_uid))

    if missing:
        raise RuntimeError(f"Missing required test pool accounts in public.users: {missing}")

    return {
        "to_upgrade": to_upgrade,
        "already_upgraded": already_upgraded,
        "viewer_legacy_verified": True,
        "skipped_hard_locked": hard_skipped,
    }


def upgrade_test_pool(
    supabase: Client,
    *,
    execute: bool = False,
    api_base: str = DEFAULT_API_BASE,
    env_out: str | Path = DEFAULT_ENV_OUT,
    repo_root: Path = REPO_ROOT,
    http_client: Optional[httpx.Client] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    target_roles: Sequence[Tuple[str, str]] = UPGRADE_POOL_ROLES,
) -> Dict[str, Any]:
    """
    Upgrade Legacy test pool accounts (00001/00002/00004/00005) via production API.
    Hard-skips VIEWER (00003) and RYAN_TEST. Default is strict Dry-Run.
    """
    env_path = Path(env_out)
    resolved_env = env_path if env_path.is_absolute() else (repo_root / env_path)
    resolved_env = resolved_env.resolve()
    tmp_path = derive_atomic_tmp_path(resolved_env)

    # Fail-closed gitignore verification BEFORE any network call or file write
    assert_git_ignored(resolved_env, "Secret env file", repo_root=repo_root)
    assert_git_ignored(tmp_path, "Atomic temp env file", repo_root=repo_root)

    preflight = inspect_pool_upgrade_preflight(supabase, target_roles=target_roles)
    to_upgrade: List[Tuple[str, str]] = preflight["to_upgrade"]

    if not execute:
        return {
            "dry_run": True,
            "preflight": preflight,
            "upgraded": [],
            "env_out": str(resolved_env),
        }

    if not to_upgrade:
        return {
            "dry_run": False,
            "preflight": preflight,
            "upgraded": [],
            "env_out": str(resolved_env),
        }

    base = api_base.rstrip("/")
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    upgraded_records: List[Dict[str, str]] = []

    own_client = http_client is None
    client = http_client or httpx.Client(timeout=UPGRADE_REQUEST_TIMEOUT_SEC)
    try:
        # Step 1: Warmup GET /api/health/deep
        health_url = f"{base}/api/health/deep"
        health_resp = client.get(
            health_url,
            headers={"User-Agent": USER_AGENT},
            timeout=UPGRADE_REQUEST_TIMEOUT_SEC,
        )
        if health_resp.status_code != 200:
            raise RuntimeError(
                f"Warmup health check failed: GET {health_url} returned HTTP {health_resp.status_code}"
            )

        # Step 2: Sequentially upgrade eligible roles with immediate atomic persistence
        session_url = f"{base}/api/auth/session"
        env_ryan = _get_env_ryan_test_id()
        for idx, (role, uid) in enumerate(to_upgrade):
            clean_loop_uid = uid.strip().lower()
            # Defense-in-depth hard lock inside loop
            if clean_loop_uid in LEGACY_PINNED_TEST_IDS:
                raise RuntimeError(f"Refusing to upgrade LEGACY_PINNED account: {uid}")
            if (
                clean_loop_uid == SYNTHETIC_RYAN_TEST_ID.lower()
                or (env_ryan and clean_loop_uid == env_ryan)
                or sha256_uid(clean_loop_uid) in {RYAN_TEST_UID_SHA256, MAIN_USER_UID_SHA256}
            ):
                raise RuntimeError(f"Refusing to re-sign protected account: {role}")

            try:
                resp = client.post(
                    session_url,
                    json={"recovery_key": uid},
                    headers=headers,
                    timeout=UPGRADE_REQUEST_TIMEOUT_SEC,
                )
            except httpx.TransportError as transport_err:
                # Re-query Supabase to detect server-side commit vs client timeout/transport drop desync
                probe = (
                    supabase.table("users")
                    .select("id, recovery_key_id, credential_version")
                    .eq("id", uid)
                    .limit(1)
                    .execute()
                )
                probe_rows = probe.data if isinstance(getattr(probe, "data", None), list) else []
                if probe_rows and probe_rows[0].get("recovery_key_id") is not None:
                    raise PartialUpgradeDesyncError(
                        f"PARTIAL_UPGRADE_DESYNC: Request failed ({type(transport_err).__name__}) for {role} ({uid}), "
                        f"but Supabase already committed recovery_key_id={probe_rows[0].get('recovery_key_id')}! "
                        f"Previously upgraded keys remain preserved in {resolved_env}."
                    ) from transport_err
                raise RuntimeError(
                    f"Request failed ({type(transport_err).__name__}) for {role} ({uid}); "
                    f"Supabase confirms recovery_key_id is still NULL."
                ) from transport_err

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Upgrade failed for {role} ({uid}): HTTP {resp.status_code} ({resp.text[:200]}). "
                    f"Already upgraded roles ({len(upgraded_records)}) are preserved in {resolved_env}."
                )

            try:
                payload = resp.json() if resp.content else {}
            except ValueError as json_err:
                raise RuntimeError(
                    f"Upgrade returned non-JSON HTTP 200 for {role} ({uid}): {resp.text[:200]}. "
                    f"Already upgraded roles ({len(upgraded_records)}) are preserved in {resolved_env}."
                ) from json_err
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"Upgrade returned non-object JSON for {role} ({uid}): {type(payload).__name__}"
                )
            upgraded_flag = payload.get("upgraded")
            recovery_key = payload.get("recovery_key")
            resp_uid = str(payload.get("user_id") or "").strip().lower()

            if (
                upgraded_flag is not True
                or not isinstance(recovery_key, str)
                or not TBJ_REC_RE.match(recovery_key.strip())
                or resp_uid != uid.lower()
            ):
                raise RuntimeError(
                    f"Invalid upgrade response for {role} ({uid}): "
                    f"upgraded={upgraded_flag!r}, user_id={resp_uid!r}, valid_key={bool(isinstance(recovery_key, str) and TBJ_REC_RE.match(recovery_key.strip()))}"
                )

            clean_key = recovery_key.strip()
            atomic_merge_write_env(
                resolved_env,
                {
                    f"TEST_USER_{role}_ID": uid.lower(),
                    f"TEST_USER_{role}_RECOVERY_KEY": clean_key,
                },
                repo_root=repo_root,
            )
            upgraded_records.append(
                {
                    "role": role,
                    "user_id": uid.lower(),
                    "masked_key": mask_recovery_key(clean_key),
                }
            )
            print(f"   ✅ Upgraded {role} ({uid}) -> {mask_recovery_key(clean_key)} (saved atomically)")

            if idx + 1 < len(to_upgrade):
                sleep_fn(UPGRADE_REQUEST_SPACING_SEC)
    finally:
        if own_client:
            client.close()

    return {
        "dry_run": False,
        "preflight": preflight,
        "upgraded": upgraded_records,
        "env_out": str(resolved_env),
    }


# ---------------------------------------------------------------------------
# CLI Presentation & Entrypoint
# ---------------------------------------------------------------------------
def _print_audit(report: Dict[str, Any]) -> None:
    print("\n" + "=" * 80)
    print("🛡️ Tabidachi Test Account Pool & Database Hygiene Audit (READ-ONLY)")
    print("=" * 80)
    print(
        f"Database Totals: users={report['total_users']} | itineraries={report['total_itineraries']} "
        f"| trip_members={report['total_trip_members']} | expenses={report['total_expenses']} "
        f"| push_subscriptions={report['total_push_subscriptions']} | notifications={report['total_notifications']}"
    )
    print(f"Main Account Protected & Present: {'YES' if report['main_account_present'] else 'MISSING!'}")
    print("\n--- Fixed 6-Account Test Pool ---")
    for item in report["pool_status"]:
        badge = "✅" if item["compliant"] else "⚠️"
        print(
            f"  {badge} {item['role']:10s} ({item['id_prefix']:18s}) | "
            f"name={str(item['name']):22s} | mode={item['actual_auth_mode']:7s} "
            f"(expected={item['expected_auth_mode']:6s}) | ver={item['credential_version']}"
        )

    ps = report["purge_summary"]
    print("\n--- Approved Purge Candidates & Orphan Summary ---")
    print(f"  Approved Target Users Qualified : {ps['qualified_users']} (disqualified: {ps['disqualified_users']})")
    print(f"  Non-UUID Test Creator Trips     : {ps['non_uuid_trips']} (exempt member rows: {ps['exempt_member_rows']})")
    print(f"  Orphan Explorer Members + Trips : {ps['orphan_explorer_pairs']}")
    print(f"  Empty SYSTEM Sample Trips (>=1h): {ps['empty_system_trips']} (cooldown-skipped: {ps['cooldown_skipped_system_trips']}, NULL-creator protected: {ps['protected_null_creator_trips']})")
    print(f"  Total Target Itineraries        : {ps['all_target_trips']}")
    print(f"  Orphan Push Subscriptions       : {ps['orphan_push_subs']}")
    print(f"  Target Notifications (incl. test-uuid & c4f87a37): {ps['target_notifications']} (unapproved historical orphans untouched: {ps['unapproved_orphan_notifs']})")
    print(f"  Cloudinary Assets to Destroy    : {ps['cloudinary_assets']}")

    suspects = report["new_suspect_accounts"]
    print(f"\n--- Unlisted Suspect Test Accounts (Audit Only, Never Auto-Purged): {len(suspects)} ---")
    for s in suspects[:15]:
        print(f"  - {s['id_prefix']} | name={s['name']!r} | created_at={s['created_at']}")
    print("=" * 80 + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage Tabidachi fixed 6-account test pool and safely purge approved test/orphan records."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit", action="store_true", help="Read-only audit of 6-account pool and orphans.")
    mode.add_argument("--purge", action="store_true", help="Purge approved test accounts & orphans (Dry-Run unless --execute).")
    mode.add_argument("--upgrade-pool", action="store_true", help="Upgrade 4 Legacy pool roles via API (Dry-Run unless --execute).")

    parser.add_argument("--execute", action="store_true", default=False, help="Apply mutations (default: strict Dry-Run).")
    parser.add_argument(
        "--backup-path",
        type=str,
        default=None,
        help="Redacted JSON backup path strictly inside docs/migrations/backups/.",
    )
    parser.add_argument(
        "--write-backup",
        action="store_true",
        default=False,
        help="Write redacted JSON backup during --purge Dry-Run as well (always written on --execute).",
    )
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE, help="Production API base URL for --upgrade-pool.")
    parser.add_argument("--env-out", type=str, default=DEFAULT_ENV_OUT, help="Gitignored local env file for upgraded keys.")

    args = parser.parse_args(argv)
    supabase = get_supabase_client()

    if args.audit:
        snapshot = load_database_snapshot(supabase, include_auth_status=True)
        report = build_audit_report(snapshot)
        _print_audit(report)
        return 0

    if args.purge:
        snapshot = load_database_snapshot(supabase, include_auth_status=False)
        plan = build_purge_plan(snapshot)
        target_items = fetch_rows_by_in_chunks(
            supabase,
            "itinerary_items",
            SAFE_SELECT_COLS["itinerary_items"],
            "itinerary_id",
            uuid_only(plan["all_target_trip_ids"]),
        )
        backup_payload = build_redacted_backup_payload(plan, target_items)
        default_backup = (
            f"docs/migrations/backups/test_accounts_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        )
        target_backup_arg = args.backup_path or default_backup
        safe_backup_path = resolve_safe_backup_path(target_backup_arg)
        assert_git_ignored(safe_backup_path, "Backup file")

        serialized_preview = json.dumps(backup_payload, indent=2, ensure_ascii=False)
        preview_sha = hashlib.sha256(serialized_preview.encode("utf-8")).hexdigest()

        print("\n" + "=" * 80)
        print(f"🛡️ Tabidachi Test Accounts Purge ({'EXECUTE' if args.execute else 'DRY-RUN'})")
        print("=" * 80)
        print(f"  Qualified Target Users          : {len(plan['qualified_user_ids'])} (disqualified: {len(plan['disqualified_users'])})")
        for dq in plan["disqualified_users"]:
            print(f"    ⚠️ Disqualified {dq['user_id']}: {dq['reason']}")
        print(f"  Non-UUID Test Creator Trips     : {len(plan['non_uuid_trip_ids'])}")
        print(f"  Exempt Orphan Member Rows       : {len(plan['exempt_member_rows'])}")
        print(f"  Orphan Explorer Members / Trips : {len(plan['orphan_explorer_members'])} / {len(plan['orphan_explorer_trip_ids'])}")
        print(f"  Empty SYSTEM Sample Trips (>=1h): {len(plan['empty_system_trip_ids'])} (NULL-creator protected: {plan['skipped_null_creator_trips_count']}, <1h skipped: {plan['skipped_recent_system_trips_count']})")
        print(f"  Total Target Itineraries        : {len(plan['all_target_trip_ids'])}")
        print(f"  Total Target Itinerary Items    : {len(target_items)}")
        print(f"  Total Target Expenses           : {len(plan['target_expenses'])}")
        print(f"  Total Target Capsules           : {len(plan['target_capsules'])}")
        print(f"  Total Target Members            : {len(plan['target_members'])}")
        print(f"  Total Target Notifications      : {len(plan['target_notifications'])} (unapproved historical orphans untouched: {plan['unapproved_orphan_notifs_count']})")
        print(f"  Total Orphan Push Subscriptions : {len(plan['orphan_push_subs'])}")
        print(f"  Total Cloudinary Assets         : {len(plan['cloudinary_urls'])}")
        print(f"  Redacted Backup Preview         : {len(serialized_preview):,} bytes | SHA256={preview_sha[:16]}...")

        if not args.execute:
            if args.write_backup:
                written_path, digest = write_redacted_backup(backup_payload, safe_backup_path)
                print(f"  💾 Dry-Run Redacted Backup Saved: {written_path} (SHA256={digest[:16]}...)")
            print("\n🛡️ [DRY RUN COMPLETED - ZERO MUTATIONS APPLIED]")
            print("=" * 80 + "\n")
            return 0

        written_path, digest = write_redacted_backup(backup_payload, safe_backup_path)
        print(f"  💾 Redacted Physical Backup Saved: {written_path} (SHA256={digest[:16]}...)")
        result = execute_purge(supabase, plan, target_items)
        print("\n🎉 [PURGE EXECUTION COMPLETE]")
        print(f"  Deleted counts     : {result['counts']}")
        print(f"  Cloudinary results : {result['cloudinary_results']}")
        print("=" * 80 + "\n")
        return 0

    if args.upgrade_pool:
        result = upgrade_test_pool(
            supabase,
            execute=args.execute,
            api_base=args.api_base,
            env_out=args.env_out,
        )
        print("\n" + "=" * 80)
        print(f"🛡️ Tabidachi Fixed Test Pool Upgrade ({'EXECUTE' if args.execute else 'DRY-RUN'})")
        print("=" * 80)
        print(f"  Pending Legacy Upgrades : {[r for r, _ in result['preflight']['to_upgrade']]}")
        print(f"  Already Upgraded (Skip) : {[r for r, _ in result['preflight']['already_upgraded']]}")
        print(f"  Hard-Locked Skip        : {result['preflight']['skipped_hard_locked']}")
        print(f"  Target Env Output       : {result['env_out']}")
        if result["dry_run"]:
            print("\n🛡️ [DRY RUN COMPLETED - ZERO HTTP CALLS OR FILE WRITES]")
        else:
            print(f"\n🎉 [UPGRADE COMPLETE] Upgraded {len(result['upgraded'])} account(s).")
        print("=" * 80 + "\n")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
