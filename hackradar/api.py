"""FastAPI backend for HackRadar V2.

Endpoints:
  GET  /api/health                   server + db sanity check
  POST /api/scans                    kick off a scan in the background
  GET  /api/scans                    list recent scans (newest first)
  GET  /api/scans/{id}               single scan + scored items
  GET  /api/scans/latest             latest finished scan + scored items
  GET  /api/items/{id}               single item + chats
  POST /api/items/{id}/chat          (reserved for Pass 3 — wired in Phase III)
  GET  /api/sources/health           per-source health table

Design notes:
  - Scan execution lives in hackradar.main.run_scan. The API just creates the
    scan row, hands it off to a BackgroundTask, and returns the scan_id.
  - The frontend polls GET /api/scans/{id} to track status. SSE streaming is
    a Phase III enhancement.
  - Only one scan can run at a time. POST /api/scans returns 409 if a scan
    is already in flight.
  - CORS is wide-open because this is a localhost-only desktop app.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from hackradar import config, db
from hackradar.main import run_scan
from hackradar.scoring.providers.anthropic import AnthropicProvider
from hackradar.scoring.providers.base import ProviderError, RateLimitError
from hackradar.sources import get_all_sources

logger = logging.getLogger("hackradar.api")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

app = FastAPI(title="HackRadar V2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    await db.init()
    logger.info("HackRadar API started. DB at %s", config.DB_PATH)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    """POST /api/scans body. All fields optional — sensible defaults applied."""

    from_date: Optional[str] = Field(None, description="YYYY-MM-DD window start")
    to_date: Optional[str] = Field(None, description="YYYY-MM-DD window end")
    lookback_hours: Optional[int] = Field(
        None, description="Alternative to from/to: scan the last N hours"
    )
    source: Optional[str] = Field(None, description="Single-source filter")
    enrich: bool = Field(True, description="Run GitHub/HF enrichment")
    focus_prompt: Optional[str] = Field(
        None, description="Free-text override sent to Pass 2"
    )


class ScanCreated(BaseModel):
    scan_id: int
    status: str
    window_start: str
    window_end: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Sanity check: server is up, DB is reachable, required keys are present."""
    missing = config.validate_keys()
    return {
        "ok": True,
        "db_path": str(config.DB_PATH),
        "missing_keys": missing,
        "sources_count": len(get_all_sources()),
    }


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _resolve_window(req: ScanRequest) -> tuple[datetime, datetime]:
    if req.from_date and req.to_date:
        return (
            _parse_date(req.from_date),
            _parse_date(req.to_date) + timedelta(hours=23, minutes=59),
        )
    end = datetime.now(timezone.utc)
    hours = req.lookback_hours or config.LOOKBACK_HOURS
    return end - timedelta(hours=hours), end


async def _run_scan_background(
    *,
    scan_id: int,
    window_start: datetime,
    window_end: datetime,
    source_filter: Optional[str],
    enrich: bool,
) -> None:
    """Background task body. Wraps run_scan with error capture so a crash
    still finishes the scan row instead of leaving status='running' forever."""
    try:
        await run_scan(
            window_start=window_start,
            window_end=window_end,
            source_filter=source_filter,
            dry_run=False,
            enrich=enrich,
            scan_id=scan_id,
        )
    except Exception as exc:
        logger.exception("Scan %d crashed", scan_id)
        try:
            await db.finish_scan(
                scan_id,
                status="error",
                items_found=0,
                items_scored=0,
                error=f"{type(exc).__name__}: {exc}"[:500],
            )
        except Exception:
            logger.exception("Failed to mark scan %d as errored", scan_id)


@app.post("/api/scans", response_model=ScanCreated, status_code=202)
async def create_scan(req: ScanRequest, background: BackgroundTasks) -> ScanCreated:
    """Kick off a scan. Returns immediately with the scan_id."""
    if await db.any_scan_running():
        raise HTTPException(
            status_code=409,
            detail="A scan is already running. Wait for it to finish.",
        )

    missing = config.validate_keys()
    if missing:
        raise HTTPException(
            status_code=412,
            detail=f"Missing API keys: {', '.join(missing)}",
        )

    window_start, window_end = _resolve_window(req)

    sources = get_all_sources()
    if req.source:
        sources = [(n, fn) for n, fn in sources if n == req.source]
        if not sources:
            raise HTTPException(404, f"Unknown source: {req.source}")
    source_names = [n for n, _ in sources]

    scan_id = await db.create_scan(
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        sources=source_names,
        focus_prompt=req.focus_prompt,
    )

    background.add_task(
        _run_scan_background,
        scan_id=scan_id,
        window_start=window_start,
        window_end=window_end,
        source_filter=req.source,
        enrich=req.enrich,
    )

    return ScanCreated(
        scan_id=scan_id,
        status="running",
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
    )


@app.get("/api/scans")
async def list_scans(limit: int = 50) -> dict[str, Any]:
    rows = await db.list_scans(limit=limit)
    return {"scans": [_scan_row_to_dict(r) for r in rows]}


@app.get("/api/scans/latest")
async def latest_scan(min_score: float = 0.0, limit: int = 100) -> dict[str, Any]:
    scan_id = await db.latest_finished_scan_id()
    if scan_id is None:
        raise HTTPException(404, "No finished scans yet. Run one first.")
    return await get_scan(scan_id, min_score=min_score, limit=limit)


@app.get("/api/scans/{scan_id}")
async def get_scan(
    scan_id: int, min_score: float = 0.0, limit: int = 100
) -> dict[str, Any]:
    scan = await db.get_scan(scan_id)
    if scan is None:
        raise HTTPException(404, f"Scan {scan_id} not found")
    items = await db.get_items_for_scan(scan_id, min_score=min_score, limit=limit)
    return {
        "scan": _scan_row_to_dict(scan),
        "items": [_item_row_to_dict(r) for r in items],
    }


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@app.get("/api/items/{item_id}")
async def get_item(item_id: int) -> dict[str, Any]:
    item = await db.get_item(item_id)
    if item is None:
        raise HTTPException(404, f"Item {item_id} not found")
    chats = await db.get_chats_for_item(item_id)
    return {
        "item": _item_row_to_dict(item),
        "chats": [dict(c) for c in chats],
    }


# ---------------------------------------------------------------------------
# Pass 3 chat — Anthropic streaming
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., description="User's next turn")


CHAT_SYSTEM_PROMPT = (
    "You are a hackathon technology scout assistant. The user is a CS student "
    "who wins hackathons by finding bleeding-edge open-source tech and building "
    "interactive demos. They have Claude Code, free T4 GPUs, and React/Next.js "
    "experience. Be specific and concrete: name files, libraries, exact commands. "
    "When asked for hackathon ideas, give a single sharp pitch — what the demo "
    "looks like, the tech stack, the wow moment, the buildability gotchas."
)


def _build_chat_system(item_row: dict[str, Any], scored: dict[str, Any]) -> str:
    bits = [CHAT_SYSTEM_PROMPT, "", "ITEM CONTEXT:"]
    bits.append(f"Title: {item_row.get('title')}")
    if item_row.get("description"):
        bits.append(f"Description: {item_row['description'][:800]}")
    for url_field in ("source_url", "github_url", "huggingface_url", "paper_url", "demo_url"):
        if item_row.get(url_field):
            bits.append(f"{url_field}: {item_row[url_field]}")
    if item_row.get("stars") is not None:
        bits.append(f"GitHub stars: {item_row['stars']}")
    if item_row.get("language"):
        bits.append(f"Primary language: {item_row['language']}")
    if scored:
        if scored.get("summary"):
            bits.append(f"Pass 2 summary: {scored['summary']}")
        if scored.get("hackathon_idea"):
            bits.append(f"Pass 2 hackathon idea: {scored['hackathon_idea']}")
    return "\n".join(bits)


def _provider_factory():
    """Indirection for tests to swap in a fake provider."""
    return AnthropicProvider()


@app.post("/api/items/{item_id}/chat")
async def chat_with_item(item_id: int, req: ChatRequest):
    """Streamed Pass 3 chat over SSE.

    Client posts {"message": "..."}. Server replies with text/event-stream.
    Each event has data=<chunk>. Final event has data=[DONE].

    Rate limited to PASS3_RATE_LIMIT_PER_HOUR user turns globally (not per
    item) to keep the daily Anthropic spend bounded.
    """
    item = await db.get_item(item_id)
    if item is None:
        raise HTTPException(404, f"Item {item_id} not found")

    # Client-side rate limit: count user turns in the last hour.
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent = await db.count_recent_chats(since_iso=one_hour_ago)
    if recent >= config.PASS3_RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            429,
            f"Pass 3 rate limit hit ({recent}/{config.PASS3_RATE_LIMIT_PER_HOUR} "
            "user turns in the last hour). Try again later.",
        )

    history = await db.get_chats_for_item(item_id)
    messages = [{"role": c["role"], "content": c["content"]} for c in history]
    messages.append({"role": "user", "content": req.message})

    # Persist the user turn before streaming so it counts toward the rate limit.
    await db.append_chat(item_id, "user", req.message)

    # Get the most recent Pass 2 score (if any) for richer system context.
    scored: dict[str, Any] = {}
    item_data = dict(item)
    # Fetch the latest score row for context — best-effort, ignore errors.
    try:
        latest_scan_id = await db.latest_finished_scan_id()
        if latest_scan_id is not None:
            rows = await db.get_items_for_scan(latest_scan_id, limit=500)
            for r in rows:
                if r.get("id") == item_id:
                    scored = r
                    break
    except Exception:
        pass

    system = _build_chat_system(item_data, scored)
    provider = _provider_factory()

    async def event_generator():
        collected: list[str] = []
        try:
            async for chunk in provider.chat_stream(messages=messages, system=system):
                collected.append(chunk)
                yield {"event": "chunk", "data": chunk}
        except RateLimitError as exc:
            yield {"event": "error", "data": f"rate_limited: {exc}"}
        except ProviderError as exc:
            yield {"event": "error", "data": f"provider_error: {exc}"}
        except Exception as exc:  # pragma: no cover
            logger.exception("Chat stream crashed")
            yield {"event": "error", "data": f"unhandled: {exc}"}
        else:
            # Persist the assembled assistant turn on clean completion.
            full = "".join(collected)
            if full:
                try:
                    await db.append_chat(item_id, "assistant", full)
                except Exception:
                    logger.exception("Failed to persist assistant turn")
            yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Source health
# ---------------------------------------------------------------------------

@app.get("/api/sources/health")
async def sources_health() -> dict[str, Any]:
    rows = await db.get_all_source_health()
    return {
        "sources": [
            {
                **dict(r),
                "status": "RED" if r["consecutive_failures"] >= 2 else "OK",
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# Row → JSON helpers
# ---------------------------------------------------------------------------

def _scan_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for field in ("sources", "progress"):
        val = out.get(field)
        if isinstance(val, str) and val:
            try:
                out[field] = json.loads(val)
            except json.JSONDecodeError:
                pass
    return out


def _item_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    val = out.get("all_sources")
    if isinstance(val, str) and val:
        try:
            out["all_sources"] = json.loads(val)
        except json.JSONDecodeError:
            out["all_sources"] = []
    if isinstance(out.get("has_demo_space"), int):
        out["has_demo_space"] = bool(out["has_demo_space"])
    return out
