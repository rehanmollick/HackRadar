"""db.py — Async SQLite DAO for HackRadar V2.

Rules enforced here:
  1. WAL mode + busy_timeout + synchronous=NORMAL applied on every connection.
  2. One aiosqlite connection per operation. No shared connection.
  3. Never hold a write transaction across an await boundary — each function
     is "open → do DB work → close" with no network/LLM calls in the middle.
  4. content_hash is computed ONCE at first-seen and never recomputed. On
     re-seen items, URLs merge into the existing row but the hash stays.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import aiosqlite

from hackradar import config

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_title(title: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for stable title hashing."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def compute_content_hash(
    *,
    github_url: Optional[str],
    huggingface_url: Optional[str],
    paper_url: Optional[str],
    source_url: Optional[str],
    title: str,
) -> str:
    """Compute a permanent cross-scan identifier for an item.

    Priority: github_url → huggingface_url → paper_url → source_url → normalized title.
    demo_url is intentionally ignored (too volatile).
    """
    for candidate in (github_url, huggingface_url, paper_url, source_url):
        if candidate:
            return hashlib.sha1(candidate.encode("utf-8")).hexdigest()
    normalized = _normalize_title(title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


@asynccontextmanager
async def _connect() -> AsyncIterator[aiosqlite.Connection]:
    """Open a new connection with WAL pragmas applied. Use as async context manager."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = aiosqlite.Row
        yield conn


async def init() -> None:
    """Apply all numbered migrations in order.

    0001_initial.sql is idempotent via CREATE TABLE IF NOT EXISTS.
    Later migrations use ALTER TABLE ADD COLUMN, which SQLite doesn't
    support with IF NOT EXISTS — so we execute statements one at a time
    and swallow "duplicate column" errors, making the whole thing
    idempotent across restarts.
    """
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with _connect() as db:
        for sql_path in migration_files:
            schema_sql = sql_path.read_text()
            # Split on ';' + newline so we can catch per-statement errors.
            statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
            for stmt in statements:
                try:
                    await db.execute(stmt)
                except aiosqlite.OperationalError as e:
                    msg = str(e).lower()
                    # These are the "already-applied" cases — safe to skip.
                    if (
                        "duplicate column" in msg
                        or "already exists" in msg
                    ):
                        continue
                    raise
        await db.commit()


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------

async def create_scan(
    *,
    window_start: str,
    window_end: str,
    sources: list[str],
    focus_prompt: Optional[str] = None,
) -> int:
    async with _connect() as db:
        cursor = await db.execute(
            """
            INSERT INTO scans (
                window_start, window_end, sources, status,
                focus_prompt, started_at
            ) VALUES (?, ?, ?, 'running', ?, ?)
            """,
            (
                window_start,
                window_end,
                json.dumps(sources),
                focus_prompt,
                _now_iso(),
            ),
        )
        await db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


async def update_scan_progress(scan_id: int, progress: dict[str, Any]) -> None:
    async with _connect() as db:
        await db.execute(
            "UPDATE scans SET progress = ? WHERE id = ?",
            (json.dumps(progress), scan_id),
        )
        await db.commit()


async def finish_scan(
    scan_id: int,
    *,
    status: str,
    items_found: int,
    items_scored: int,
    error: Optional[str] = None,
) -> None:
    async with _connect() as db:
        await db.execute(
            """
            UPDATE scans
            SET status = ?, items_found = ?, items_scored = ?,
                error = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, items_found, items_scored, error, _now_iso(), scan_id),
        )
        await db.commit()


async def get_scan(scan_id: int) -> Optional[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def any_scan_running() -> bool:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) AS n FROM scans WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        return bool(row and row["n"] > 0)


async def list_scans(limit: int = 50) -> list[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM scans ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def latest_finished_scan_id() -> Optional[int]:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT id FROM scans WHERE status = 'done' "
            "ORDER BY finished_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return int(row["id"]) if row else None


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

async def upsert_item(item_data: dict[str, Any]) -> int:
    """Insert a new item or merge URLs into an existing row.

    Matching rule (in priority order):
      1. If any of the new item's URLs overlap with an existing row's URLs,
         merge into that row. This handles the TRIBE v2 case where scan #1
         finds the blog only and scan #2 also finds HF + GitHub.
      2. Else, compute content_hash and look for a row with that hash
         (catches the title-fallback + all-null-URL case).
      3. Else insert a new row with a freshly computed content_hash.

    In all merge paths the existing row's content_hash stays untouched —
    the hash is a stable ID from first-seen time, not a match key.
    """
    new_urls = [
        item_data.get("github_url"),
        item_data.get("huggingface_url"),
        item_data.get("paper_url"),
        item_data.get("source_url"),
        item_data.get("demo_url"),
    ]
    new_urls = [u for u in new_urls if u]

    now = _now_iso()

    async with _connect() as db:
        existing = None

        # Step 1: URL-overlap match
        if new_urls:
            placeholders = ",".join("?" * len(new_urls))
            query = (
                "SELECT id, content_hash, all_sources, github_url, huggingface_url, "
                "demo_url, paper_url, source_url FROM items WHERE "
                f"source_url IN ({placeholders}) "
                f"OR github_url IN ({placeholders}) "
                f"OR huggingface_url IN ({placeholders}) "
                f"OR paper_url IN ({placeholders}) "
                f"OR demo_url IN ({placeholders}) "
                "LIMIT 1"
            )
            params = tuple(new_urls) * 5
            cursor = await db.execute(query, params)
            existing = await cursor.fetchone()

        # Step 2: content_hash match (title-fallback case)
        if existing is None:
            content_hash = compute_content_hash(
                github_url=item_data.get("github_url"),
                huggingface_url=item_data.get("huggingface_url"),
                paper_url=item_data.get("paper_url"),
                source_url=item_data.get("source_url"),
                title=item_data["title"],
            )
            cursor = await db.execute(
                "SELECT id, content_hash, all_sources, github_url, huggingface_url, "
                "demo_url, paper_url, source_url FROM items WHERE content_hash = ?",
                (content_hash,),
            )
            existing = await cursor.fetchone()
        else:
            content_hash = compute_content_hash(
                github_url=item_data.get("github_url"),
                huggingface_url=item_data.get("huggingface_url"),
                paper_url=item_data.get("paper_url"),
                source_url=item_data.get("source_url"),
                title=item_data["title"],
            )

        if existing is None:
            cursor = await db.execute(
                """
                INSERT INTO items (
                    content_hash, title, description, date, category, source,
                    source_url, github_url, huggingface_url, demo_url, paper_url,
                    all_sources, stars, language, license, readme_excerpt,
                    model_size, downloads, has_demo_space, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_hash,
                    item_data["title"],
                    item_data.get("description"),
                    item_data["date"],
                    item_data.get("category"),
                    item_data.get("source"),
                    item_data.get("source_url"),
                    item_data.get("github_url"),
                    item_data.get("huggingface_url"),
                    item_data.get("demo_url"),
                    item_data.get("paper_url"),
                    json.dumps(item_data.get("all_sources") or []),
                    item_data.get("stars"),
                    item_data.get("language"),
                    item_data.get("license"),
                    item_data.get("readme_excerpt"),
                    item_data.get("model_size"),
                    item_data.get("downloads"),
                    int(item_data["has_demo_space"]) if item_data.get("has_demo_space") is not None else None,
                    now,
                    now,
                ),
            )
            await db.commit()
            assert cursor.lastrowid is not None
            return cursor.lastrowid

        # Merge path: keep existing hash, merge URLs and all_sources.
        existing_sources: list[str] = []
        try:
            existing_sources = json.loads(existing["all_sources"] or "[]")
        except (json.JSONDecodeError, TypeError):
            existing_sources = []
        new_sources = item_data.get("all_sources") or []
        merged_sources = list(dict.fromkeys([*existing_sources, *new_sources]))

        merged = {
            "source_url": existing["source_url"] or item_data.get("source_url"),
            "github_url": existing["github_url"] or item_data.get("github_url"),
            "huggingface_url": existing["huggingface_url"] or item_data.get("huggingface_url"),
            "demo_url": existing["demo_url"] or item_data.get("demo_url"),
            "paper_url": existing["paper_url"] or item_data.get("paper_url"),
        }

        await db.execute(
            """
            UPDATE items
            SET source_url = ?, github_url = ?, huggingface_url = ?,
                demo_url = ?, paper_url = ?, all_sources = ?, last_seen = ?
            WHERE id = ?
            """,
            (
                merged["source_url"],
                merged["github_url"],
                merged["huggingface_url"],
                merged["demo_url"],
                merged["paper_url"],
                json.dumps(merged_sources),
                now,
                existing["id"],
            ),
        )
        await db.commit()
        return int(existing["id"])


async def get_item(item_id: int) -> Optional[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_items_for_scan(
    scan_id: int,
    *,
    min_score: float = 0.0,
    limit: int = 200,
) -> list[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute(
            """
            SELECT items.*,
                   scores.total_score, scores.summary,
                   scores.usability_score, scores.innovation_score,
                   scores.underexploited_score, scores.wow_score,
                   scores.what_the_tech_does, scores.key_capabilities,
                   scores.idea_sparks, scores.prompt_version,
                   scores.open_score, scores.novelty_score,
                   scores.build_score, scores.hackathon_idea,
                   scores.tech_stack, scores.why_now, scores.effort_estimate,
                   scores.provider, scores.model
            FROM items
            JOIN scores ON scores.item_id = items.id
            WHERE scores.scan_id = ? AND scores.pass = 2 AND scores.total_score >= ?
            ORDER BY scores.total_score DESC
            LIMIT ?
            """,
            (scan_id, min_score, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

async def record_score(
    *,
    item_id: int,
    scan_id: int,
    pass_num: int,
    provider: str,
    model: str,
    # Rev 3.1 rubric fields (primary).
    usability_score: Optional[float] = None,
    innovation_score: Optional[float] = None,
    underexploited_score: Optional[float] = None,
    wow_score: Optional[float] = None,
    total_score: Optional[float] = None,
    summary: Optional[str] = None,
    what_the_tech_does: Optional[str] = None,
    key_capabilities: Optional[list[str]] = None,
    idea_sparks: Optional[list[str]] = None,
    prompt_version: Optional[str] = None,
    raw_response: Optional[str] = None,
) -> int:
    """Insert a rev 3.1 score row.

    `key_capabilities` and `idea_sparks` are serialized to JSON strings
    for storage. Read-side deserializes in the API layer.
    """
    key_caps_json = json.dumps(key_capabilities) if key_capabilities else None
    idea_sparks_json = json.dumps(idea_sparks) if idea_sparks else None
    async with _connect() as db:
        cursor = await db.execute(
            """
            INSERT INTO scores (
                item_id, scan_id, pass, provider, model,
                usability_score, innovation_score, underexploited_score,
                wow_score, total_score,
                summary, what_the_tech_does, key_capabilities, idea_sparks,
                prompt_version, raw_response, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id, scan_id, pass_num, provider, model,
                usability_score, innovation_score, underexploited_score,
                wow_score, total_score,
                summary, what_the_tech_does, key_caps_json, idea_sparks_json,
                prompt_version, raw_response, _now_iso(),
            ),
        )
        await db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# Source health
# ---------------------------------------------------------------------------

async def record_source_health(
    *,
    source: str,
    success: bool,
    last_error: Optional[str] = None,
    at: Optional[str] = None,
) -> None:
    at = at or _now_iso()
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM source_health WHERE source = ?", (source,)
        )
        existing = await cursor.fetchone()

        if existing is None:
            await db.execute(
                """
                INSERT INTO source_health (
                    source, last_success, last_failure, last_error,
                    consecutive_failures, total_runs, total_failures
                ) VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    source,
                    at if success else None,
                    None if success else at,
                    None if success else last_error,
                    0 if success else 1,
                    0 if success else 1,
                ),
            )
        else:
            if success:
                await db.execute(
                    """
                    UPDATE source_health
                    SET last_success = ?, consecutive_failures = 0,
                        total_runs = total_runs + 1
                    WHERE source = ?
                    """,
                    (at, source),
                )
            else:
                await db.execute(
                    """
                    UPDATE source_health
                    SET last_failure = ?, last_error = ?,
                        consecutive_failures = consecutive_failures + 1,
                        total_runs = total_runs + 1,
                        total_failures = total_failures + 1
                    WHERE source = ?
                    """,
                    (at, last_error, source),
                )
        await db.commit()


async def get_all_source_health() -> list[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM source_health ORDER BY source"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

async def append_chat(item_id: int, role: str, content: str) -> int:
    async with _connect() as db:
        cursor = await db.execute(
            "INSERT INTO chats (item_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (item_id, role, content, _now_iso()),
        )
        await db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


async def get_chats_for_item(item_id: int) -> list[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM chats WHERE item_id = ? ORDER BY created_at ASC",
            (item_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def count_recent_chats(item_id: Optional[int] = None, since_iso: Optional[str] = None) -> int:
    """Count chat turns. Used for client-side Pass 3 rate limiting."""
    async with _connect() as db:
        if since_iso and item_id is not None:
            cursor = await db.execute(
                "SELECT COUNT(*) AS n FROM chats WHERE item_id = ? AND created_at >= ? AND role = 'user'",
                (item_id, since_iso),
            )
        elif since_iso:
            cursor = await db.execute(
                "SELECT COUNT(*) AS n FROM chats WHERE created_at >= ? AND role = 'user'",
                (since_iso,),
            )
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) AS n FROM chats WHERE role = 'user'"
            )
        row = await cursor.fetchone()
        return int(row["n"]) if row else 0
