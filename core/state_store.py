"""
State Store
───────────
Async SQLite database for all pipeline data.
- chunks          : scraped and filtered content
- agent_outputs   : every LLM call result with metadata
- thought_chain   : full lineage from scrape → triage → analyst → synthesis
- query_cache     : semantic cache for repeat/similar queries (future use)

WAL mode ensures concurrent reads don't block writes.
All operations are fire-and-forget safe — failures are logged, never raised.
"""

import aiosqlite
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)
DB_PATH = "zhenyi.db"


async def init_db(db_path: str = DB_PATH):
    """Create all tables. Safe to call multiple times — uses IF NOT EXISTS."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;

                CREATE TABLE IF NOT EXISTS chunks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id    TEXT    NOT NULL,
                    source      TEXT,
                    url         TEXT,
                    content     TEXT,
                    relevance_score REAL DEFAULT 0,
                    created_at  REAL
                );

                CREATE TABLE IF NOT EXISTS agent_outputs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id    TEXT    NOT NULL,
                    agent_id    TEXT,
                    provider    TEXT,
                    model       TEXT,
                    input_tokens  INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    latency_ms  REAL,
                    output_json TEXT,
                    created_at  REAL
                );

                CREATE TABLE IF NOT EXISTS thought_chain (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id    TEXT    NOT NULL,
                    step        TEXT,
                    note        TEXT,
                    created_at  REAL
                );

                CREATE TABLE IF NOT EXISTS queries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id    TEXT    NOT NULL UNIQUE,
                    query_text  TEXT,
                    profile     TEXT,
                    plan_json   TEXT,
                    answer      TEXT,
                    confidence  REAL,
                    duration_ms REAL,
                    created_at  REAL
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_query ON chunks(query_id);
                CREATE INDEX IF NOT EXISTS idx_outputs_query ON agent_outputs(query_id);
                CREATE INDEX IF NOT EXISTS idx_chain_query ON thought_chain(query_id);
            """)
            await db.commit()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")


async def save_chunks(query_id: str, chunks: list[dict], db_path: str = DB_PATH):
    """Save filtered chunks to database."""
    if not chunks:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            for c in chunks:
                await db.execute(
                    "INSERT INTO chunks "
                    "(query_id, source, url, content, relevance_score, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        query_id,
                        c.get("source", "unknown"),
                        c.get("url", ""),
                        c.get("content", "")[:4000],
                        c.get("relevance_score", 0.0),
                        time.time(),
                    )
                )
            await db.commit()
    except Exception as e:
        logger.error(f"save_chunks error: {e}")


async def log_agent_output(
    query_id: str,
    agent_id: str,
    provider: str,
    model: str,
    latency_ms: float,
    output: dict,
    db_path: str = DB_PATH,
):
    """Log what an agent returned. Non-fatal on failure."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO agent_outputs "
                "(query_id, agent_id, provider, model, latency_ms, output_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    query_id, agent_id, provider, model,
                    latency_ms,
                    json.dumps(output, ensure_ascii=False)[:2000],
                    time.time(),
                )
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"log_agent_output error (non-fatal): {e}")


async def log_thought(
    query_id: str,
    step: str,
    note: str,
    db_path: str = DB_PATH,
):
    """Add a step to the thought chain — full lineage tracking."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO thought_chain (query_id, step, note, created_at) "
                "VALUES (?, ?, ?, ?)",
                (query_id, step, str(note)[:1000], time.time())
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"log_thought error (non-fatal): {e}")


async def save_query_result(
    query_id: str,
    query_text: str,
    profile: str,
    plan: dict,
    answer: str,
    confidence: float,
    duration_ms: float,
    db_path: str = DB_PATH,
):
    """Save the final query result for history and caching."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO queries "
                "(query_id, query_text, profile, plan_json, answer, confidence, duration_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    query_id, query_text, profile,
                    json.dumps(plan, ensure_ascii=False),
                    answer[:8000], confidence, duration_ms, time.time()
                )
            )
            await db.commit()
    except Exception as e:
        logger.error(f"save_query_result error: {e}")


async def get_thought_chain(query_id: str, db_path: str = DB_PATH) -> list[dict]:
    """Retrieve the full thought chain for a query."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT step, note, created_at FROM thought_chain "
                "WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_thought_chain error: {e}")
        return []


async def get_recent_queries(limit: int = 10, db_path: str = DB_PATH) -> list[dict]:
    """Retrieve recent query history."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT query_id, query_text, profile, confidence, duration_ms, created_at "
                "FROM queries ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_recent_queries error: {e}")
        return []
