-- HackRadar V2 initial schema.
-- Run via `CREATE TABLE IF NOT EXISTS` on startup. One file for V2.0.
-- V2.1+ adds numbered files and a schema_version table.

CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY,
    content_hash    TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    date            TEXT NOT NULL,
    category        TEXT,
    source          TEXT,
    source_url      TEXT,
    github_url      TEXT,
    huggingface_url TEXT,
    demo_url        TEXT,
    paper_url       TEXT,
    all_sources     TEXT,
    stars           INTEGER,
    language        TEXT,
    license         TEXT,
    readme_excerpt  TEXT,
    model_size      TEXT,
    downloads       INTEGER,
    has_demo_space  INTEGER,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_date ON items(date);
CREATE INDEX IF NOT EXISTS idx_items_first_seen ON items(first_seen);

CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY,
    window_start    TEXT NOT NULL,
    window_end      TEXT NOT NULL,
    sources         TEXT NOT NULL,
    status          TEXT NOT NULL,
    focus_prompt    TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    items_found     INTEGER,
    items_scored    INTEGER,
    error           TEXT,
    progress        TEXT
);

CREATE INDEX IF NOT EXISTS idx_scans_started_at ON scans(started_at DESC);

CREATE TABLE IF NOT EXISTS scores (
    id              INTEGER PRIMARY KEY,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    scan_id         INTEGER NOT NULL REFERENCES scans(id),
    pass            INTEGER NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    open_score      REAL,
    novelty_score   REAL,
    wow_score       REAL,
    build_score     REAL,
    total_score     REAL,
    summary         TEXT,
    hackathon_idea  TEXT,
    tech_stack      TEXT,
    why_now         TEXT,
    effort_estimate TEXT,
    raw_response    TEXT,
    scored_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scores_item_id ON scores(item_id);
CREATE INDEX IF NOT EXISTS idx_scores_scan_id ON scores(scan_id);
CREATE INDEX IF NOT EXISTS idx_scores_total ON scores(total_score DESC);

CREATE TABLE IF NOT EXISTS chats (
    id              INTEGER PRIMARY KEY,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chats_item_id ON chats(item_id);
CREATE INDEX IF NOT EXISTS idx_chats_created_at ON chats(created_at);

CREATE TABLE IF NOT EXISTS notes (
    id              INTEGER PRIMARY KEY,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    saved           INTEGER NOT NULL DEFAULT 0,
    rating          INTEGER,
    note            TEXT,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_item_id ON notes(item_id);

CREATE TABLE IF NOT EXISTS source_health (
    source                  TEXT PRIMARY KEY,
    last_success            TEXT,
    last_failure            TEXT,
    last_error              TEXT,
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    total_runs              INTEGER NOT NULL DEFAULT 0,
    total_failures          INTEGER NOT NULL DEFAULT 0
);
