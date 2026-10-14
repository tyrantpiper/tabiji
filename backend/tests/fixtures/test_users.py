"""
Standardized Test User Fixtures (5 Static Roles)
Used across FastAPI TestClient integration tests and Security Sentinel PoCs.
"""

TEST_USER_OWNER_ID = "00000000-0000-0000-0000-000000000001"
TEST_USER_EDITOR_ID = "00000000-0000-0000-0000-000000000002"
TEST_USER_VIEWER_ID = "00000000-0000-0000-0000-000000000003"
TEST_USER_CAPSULE_ID = "00000000-0000-0000-0000-000000000004"
TEST_USER_STRANGER_ID = "00000000-0000-0000-0000-000000000005"

TEST_USERS = {
    "OWNER": {"id": TEST_USER_OWNER_ID, "name": "[Test] Owner"},
    "EDITOR": {"id": TEST_USER_EDITOR_ID, "name": "[Test] Editor"},
    "VIEWER": {"id": TEST_USER_VIEWER_ID, "name": "[Test] Viewer"},
    "CAPSULE": {"id": TEST_USER_CAPSULE_ID, "name": "[Test] CapsuleTester"},
    "STRANGER": {"id": TEST_USER_STRANGER_ID, "name": "[Test] Stranger"},
}
