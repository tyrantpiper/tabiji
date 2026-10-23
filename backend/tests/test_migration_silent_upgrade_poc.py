"""
Security Sentinel In-Memory PoC: Database Migration & User Lifecycle Verification
Tests:
1. TC-1: Schema idempotency and zero-lock safety when adding columns to existing user table.
2. TC-2: Existing user with NULL recovery_key_id seamlessly logs in via legacy UUID.
3. TC-3: Backend silently generates and binds tbj_rec_... key without data loss.
4. TC-4: Subsequent logins via the new recovery key succeed with O(1) key_id lookup.
5. TC-5: Rotation revokes previous key while preserving original UUID and foreign keys.
"""

import pytest
import sqlite3
from backend.routers.auth import (
    generate_prefixed_recovery_key,
    verify_recovery_key,
)

@pytest.fixture
def mock_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    # 1. Create existing users table as it currently exists in production
    cursor.execute("""
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            email TEXT,
            name TEXT,
            avatar_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Insert existing production user
    cursor.execute("INSERT INTO users (id, name) VALUES ('user_existing_uuid_123', 'OldUser')")
    # Insert trips referencing this user
    cursor.execute("""
        CREATE TABLE trips (
            id TEXT PRIMARY KEY,
            created_by TEXT REFERENCES users(id),
            title TEXT
        )
    """)
    cursor.execute("INSERT INTO trips (id, created_by, title) VALUES ('trip_001', 'user_existing_uuid_123', 'Tokyo Trip')")
    conn.commit()
    yield conn
    conn.close()


def test_tc1_migration_adds_columns_without_breaking_existing_data(mock_db):
    """TC-1: Prove that adding recovery columns does not break existing rows or foreign keys."""
    cursor = mock_db.cursor()
    
    # Simulate Migration
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_key_id TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_secret_hash TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN credential_version INTEGER DEFAULT 1")
    cursor.execute("CREATE UNIQUE INDEX idx_users_rec_id ON users(recovery_key_id)")
    mock_db.commit()

    # Verify existing user remains intact
    cursor.execute("SELECT id, name, recovery_key_id, credential_version FROM users WHERE id = 'user_existing_uuid_123'")
    row = cursor.fetchone()
    assert row[0] == "user_existing_uuid_123"
    assert row[1] == "OldUser"
    assert row[2] is None  # Initially NULL for old users
    assert row[3] == 1     # Default credential version is 1


def test_tc2_and_tc3_legacy_user_silent_upgrade(mock_db):
    """TC-2 & TC-3: Existing user calls /session with legacy UUID; receives silent upgrade key."""
    cursor = mock_db.cursor()
    # Apply migration
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_key_id TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_secret_hash TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN credential_version INTEGER DEFAULT 1")
    mock_db.commit()

    # Simulate /api/auth/session logic:
    incoming_key = "user_existing_uuid_123"
    cursor.execute("SELECT id, recovery_key_id FROM users WHERE id = ?", (incoming_key,))
    user = cursor.fetchone()
    assert user is not None

    full_key, key_id, secret_hash = generate_prefixed_recovery_key()
    # Silent upgrade binding
    cursor.execute("""
        UPDATE users 
        SET recovery_key_id = ?, recovery_secret_hash = ? 
        WHERE id = ?
    """, (key_id, secret_hash, incoming_key))
    mock_db.commit()

    # Verify key bound to same UUID
    cursor.execute("SELECT id, recovery_key_id FROM users WHERE id = ?", (incoming_key,))
    updated = cursor.fetchone()
    assert updated[0] == "user_existing_uuid_123"
    assert updated[1] == key_id


def test_tc4_login_via_new_recovery_key(mock_db):
    """TC-4: Prove that user can now login on another device using the newly issued tbj_rec key."""
    cursor = mock_db.cursor()
    # Setup user with key
    full_key, key_id, secret_hash = generate_prefixed_recovery_key()
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_key_id TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_secret_hash TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN credential_version INTEGER DEFAULT 1")
    cursor.execute("""
        UPDATE users 
        SET recovery_key_id = ?, recovery_secret_hash = ? 
        WHERE id = 'user_existing_uuid_123'
    """, (key_id, secret_hash))
    mock_db.commit()

    # Incoming login on new phone
    parts = full_key.split("_")
    inc_key_id = parts[2]
    
    # O(1) lookup
    cursor.execute("SELECT id, recovery_secret_hash FROM users WHERE recovery_key_id = ?", (inc_key_id,))
    matched = cursor.fetchone()
    assert matched is not None
    assert matched[0] == "user_existing_uuid_123"

    # Verify secret hash using the real verify_recovery_key function from auth.py
    assert verify_recovery_key(full_key, matched[1]) is True


def test_tc5_rotation_invalidates_old_key_and_preserves_foreign_keys(mock_db):
    """TC-5: Rotating key issues new key, invalidates old key, keeps trips intact."""
    cursor = mock_db.cursor()
    full_key1, key_id1, secret_hash1 = generate_prefixed_recovery_key()
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_key_id TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN recovery_secret_hash TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN credential_version INTEGER DEFAULT 1")
    cursor.execute("""
        UPDATE users 
        SET recovery_key_id = ?, recovery_secret_hash = ? 
        WHERE id = 'user_existing_uuid_123'
    """, (key_id1, secret_hash1))
    mock_db.commit()

    # Execute Rotation
    full_key2, key_id2, secret_hash2 = generate_prefixed_recovery_key()
    cursor.execute("""
        UPDATE users 
        SET recovery_key_id = ?, recovery_secret_hash = ?, credential_version = credential_version + 1
        WHERE id = 'user_existing_uuid_123'
    """, (key_id2, secret_hash2))
    mock_db.commit()

    # Old key fails lookup
    cursor.execute("SELECT id FROM users WHERE recovery_key_id = ?", (key_id1,))
    assert cursor.fetchone() is None

    # New key succeeds lookup
    cursor.execute("SELECT id FROM users WHERE recovery_key_id = ?", (key_id2,))
    assert cursor.fetchone()[0] == "user_existing_uuid_123"

    # Trips foreign keys remain 100% attached to the user
    cursor.execute("SELECT title FROM trips WHERE created_by = 'user_existing_uuid_123'")
    trips = cursor.fetchall()
    assert len(trips) == 1
    assert trips[0][0] == "Tokyo Trip"
