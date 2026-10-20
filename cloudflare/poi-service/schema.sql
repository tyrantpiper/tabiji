-- Tabidachi Cloudflare D1 POI Pool Schema
-- Database: tabidachi-poi-db (cefda064-d8d5-4501-9f0f-a525b0a387dd)

CREATE TABLE IF NOT EXISTS user_poi_pool (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    address TEXT,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    google_place_id TEXT,
    category TEXT DEFAULT 'attraction',
    rating REAL,
    user_notes TEXT,
    source_url TEXT,
    is_pinned INTEGER DEFAULT 1,
    pin_color TEXT DEFAULT '#E56E25',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(user_id, lat, lng)
);

CREATE INDEX IF NOT EXISTS idx_poi_user_created ON user_poi_pool(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_poi_coords ON user_poi_pool(lat, lng);
