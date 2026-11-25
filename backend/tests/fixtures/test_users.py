"""
Standardized Test User Fixtures (6 Fixed Dual-Track Pool Roles)
Used across FastAPI TestClient integration tests, Security Sentinel PoCs,
and test-account lifecycle management scripts.
"""

import os
import re
from typing import Any, Dict

RFC4122_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

TEST_USER_OWNER_ID = "00000000-0000-0000-0000-000000000001"
TEST_USER_EDITOR_ID = "00000000-0000-0000-0000-000000000002"
TEST_USER_VIEWER_ID = "00000000-0000-0000-0000-000000000003"
TEST_USER_CAPSULE_ID = "00000000-0000-0000-0000-000000000004"
TEST_USER_STRANGER_ID = "00000000-0000-0000-0000-000000000005"

# Synthetic RFC 4122 v4 fallback for public source; real QA UUID is injected via env.
SYNTHETIC_RYAN_TEST_ID = "00000000-0000-4000-8000-000000000006"


def resolve_ryan_test_user_id() -> str:
    """Resolve RYAN_TEST UUID from environment, falling back to synthetic RFC 4122 v4."""
    for env_name in ("TEST_USER_RYAN_TEST_ID", "NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID"):
        raw = (os.getenv(env_name) or "").strip()
        if raw:
            if RFC4122_UUID_V4_RE.match(raw):
                return raw.lower()
            return SYNTHETIC_RYAN_TEST_ID
    return SYNTHETIC_RYAN_TEST_ID


TEST_USER_RYAN_TEST_ID = resolve_ryan_test_user_id()

TEST_USERS: Dict[str, Dict[str, Any]] = {
    "OWNER": {
        "id": TEST_USER_OWNER_ID,
        "name": "[Test] Owner",
        "auth_mode": "modern",
        "edge_shield_v4_compatible": False,
    },
    "EDITOR": {
        "id": TEST_USER_EDITOR_ID,
        "name": "[Test] Editor",
        "auth_mode": "modern",
        "edge_shield_v4_compatible": False,
    },
    "VIEWER": {
        "id": TEST_USER_VIEWER_ID,
        "name": "[Test] Viewer",
        "auth_mode": "legacy",
        "edge_shield_v4_compatible": False,
    },
    "CAPSULE": {
        "id": TEST_USER_CAPSULE_ID,
        "name": "[Test] CapsuleTester",
        "auth_mode": "modern",
        "edge_shield_v4_compatible": False,
    },
    "STRANGER": {
        "id": TEST_USER_STRANGER_ID,
        "name": "[Test] Stranger",
        "auth_mode": "modern",
        "edge_shield_v4_compatible": False,
    },
    "RYAN_TEST": {
        "id": TEST_USER_RYAN_TEST_ID,
        "name": "Ryan Test",
        "auth_mode": "modern",
        "edge_shield_v4_compatible": True,
    },
}

STATIC_ROLE_TEST_USER_IDS = (
    TEST_USER_OWNER_ID,
    TEST_USER_EDITOR_ID,
    TEST_USER_VIEWER_ID,
    TEST_USER_CAPSULE_ID,
    TEST_USER_STRANGER_ID,
)

ALL_FIXED_TEST_USER_IDS = (
    *STATIC_ROLE_TEST_USER_IDS,
    TEST_USER_RYAN_TEST_ID,
)

LEGACY_PINNED_TEST_USER_IDS = frozenset({TEST_USER_VIEWER_ID})

MODERN_UPGRADEABLE_TEST_USER_IDS = (
    TEST_USER_OWNER_ID,
    TEST_USER_EDITOR_ID,
    TEST_USER_CAPSULE_ID,
    TEST_USER_STRANGER_ID,
)
