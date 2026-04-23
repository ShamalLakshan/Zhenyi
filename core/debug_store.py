"""
Debug Store
───────────
Extended database tables for comprehensive query logging and debugging.
Stores full request/response payloads, scraper configs, agent reasoning, and orchestrator decisions.

New tables:
- api_requests   : full API request metadata and path to payload file
- api_responses  : full API response metadata and path to payload file
- scraper_invocations : scraper execution log with arguments and results
- orchestrator_plan   : orchestrator decision reasoning and model selection
- agent_reasoning     : intermediate reasoning steps from agents

All tables link to queries via query_id and are batch-inserted at pipeline end.
"""

import aiosqlite
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)
DB_PATH = "zhenyi.db"


async def init_debug_tables(db_path: str = DB_PATH):
    """Create all debug logging tables. Safe to call multiple times."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;

                -- API request metadata: what was sent to the model
                CREATE TABLE IF NOT EXISTS api_requests (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id                TEXT    NOT NULL,
                    agent_id                TEXT,
                    provider                TEXT,
                    model                   TEXT,
                    attempt                 INTEGER,
                    request_payload_path    TEXT,
                    request_headers_redacted BOOLEAN DEFAULT 1,
                    request_body_redacted   BOOLEAN DEFAULT 1,
                    estimated_tokens        INTEGER DEFAULT 0,
                    tokens_in               INTEGER DEFAULT 0,
                    payload_json            TEXT,
                    created_at              REAL,
                    batch_logged_at         REAL
                );

                -- API response metadata: what came back from the model
                CREATE TABLE IF NOT EXISTS api_responses (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id                TEXT    NOT NULL,
                    agent_id                TEXT,
                    provider                TEXT,
                    model                   TEXT,
                    attempt                 INTEGER,
                    response_payload_path   TEXT,
                    response_code           INTEGER,
                    response_redacted       BOOLEAN DEFAULT 1,
                    actual_tokens_in        INTEGER DEFAULT 0,
                    actual_tokens_out       INTEGER DEFAULT 0,
                    latency_ms              REAL,
                    error_message           TEXT,
                    payload_json            TEXT,
                    created_at              REAL,
                    batch_logged_at         REAL
                );

                -- Scraper invocation log: when scrapers were called and what they returned
                CREATE TABLE IF NOT EXISTS scraper_invocations (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id                TEXT    NOT NULL,
                    scraper_name            TEXT,
                    scraper_config_path     TEXT,
                    config_redacted         BOOLEAN DEFAULT 1,
                    start_time              REAL,
                    end_time                REAL,
                    duration_ms             REAL,
                    chunks_returned         INTEGER DEFAULT 0,
                    raw_output_path         TEXT,
                    raw_output_json         TEXT,
                    is_compressed           BOOLEAN DEFAULT 0,
                    error_message           TEXT,
                    circuit_breaker_state   TEXT,
                    created_at              REAL,
                    batch_logged_at         REAL
                );

                -- Orchestrator planning decisions
                CREATE TABLE IF NOT EXISTS orchestrator_plan (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id                TEXT    NOT NULL UNIQUE,
                    reasoning               TEXT,
                    query_profile           TEXT,
                    selected_scrapers       TEXT,
                    selected_models         TEXT,
                    plan_graph_json         TEXT,
                    plan_hash               TEXT,
                    fallback_used           BOOLEAN DEFAULT 0,
                    constraints_applied     TEXT,
                    decision_tree_path      TEXT,
                    created_at              REAL,
                    batch_logged_at         REAL
                );

                -- Intermediate reasoning: agent thinking steps and decisions
                CREATE TABLE IF NOT EXISTS agent_reasoning (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id                TEXT    NOT NULL,
                    agent_id                TEXT,
                    agent_role              TEXT,
                    step_number             INTEGER,
                    reasoning_text          TEXT,
                    decision_made           TEXT,
                    source_chunks_used      INTEGER DEFAULT 0,
                    confidence              REAL,
                    created_at              REAL,
                    batch_logged_at         REAL
                );

                -- Indexes for efficient querying
                CREATE INDEX IF NOT EXISTS idx_api_requests_query ON api_requests(query_id);
                CREATE INDEX IF NOT EXISTS idx_api_requests_provider ON api_requests(provider, model);
                CREATE INDEX IF NOT EXISTS idx_api_responses_query ON api_responses(query_id);
                CREATE INDEX IF NOT EXISTS idx_api_responses_provider ON api_responses(provider, model);
                CREATE INDEX IF NOT EXISTS idx_api_responses_error ON api_responses(error_message);
                CREATE INDEX IF NOT EXISTS idx_scraper_invocations_query ON scraper_invocations(query_id);
                CREATE INDEX IF NOT EXISTS idx_scraper_invocations_scraper ON scraper_invocations(scraper_name);
                CREATE INDEX IF NOT EXISTS idx_scraper_invocations_circuit ON scraper_invocations(circuit_breaker_state);
                CREATE INDEX IF NOT EXISTS idx_orchestrator_plan_query ON orchestrator_plan(query_id);
                CREATE INDEX IF NOT EXISTS idx_orchestrator_plan_hash ON orchestrator_plan(plan_hash);
                CREATE INDEX IF NOT EXISTS idx_agent_reasoning_query ON agent_reasoning(query_id);
                CREATE INDEX IF NOT EXISTS idx_agent_reasoning_agent ON agent_reasoning(agent_id);
            """)
            await db.commit()
        logger.info("Debug tables initialized")
    except Exception as e:
        logger.error(f"Debug tables init error: {e}")


async def log_api_request(
    query_id: str,
    agent_id: str,
    provider: str,
    model: str,
    attempt: int,
    request_payload_path: str = "",
    headers_redacted: bool = True,
    body_redacted: bool = True,
    estimated_tokens: int = 0,
    payload_dict: dict = None,
    tokens_in: int = 0,
    db_path: str = DB_PATH,
):
    """
    Log API request metadata directly to DB.
    Supports both legacy file path and new payload_dict approach.
    If payload_dict provided, it's stored as JSON; otherwise request_payload_path is stored.
    """
    try:
        payload_json = None
        if payload_dict:
            payload_json = json.dumps(payload_dict, ensure_ascii=False)[:8000]
        
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO api_requests
                (query_id, agent_id, provider, model, attempt, request_payload_path,
                 request_headers_redacted, request_body_redacted, estimated_tokens, tokens_in,
                 payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_id, agent_id, provider, model, attempt, request_payload_path or "",
                 headers_redacted, body_redacted, estimated_tokens, tokens_in,
                 payload_json, time.time())
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"log_api_request error (non-fatal): {e}")


async def log_api_response(
    query_id: str,
    agent_id: str,
    provider: str,
    model: str,
    attempt: int,
    response_payload_path: str = "",
    response_code: int = 200,
    response_redacted: bool = True,
    actual_tokens_in: int = 0,
    actual_tokens_out: int = 0,
    latency_ms: float = 0,
    error_message: str = "",
    payload_dict: dict = None,
    db_path: str = DB_PATH,
):
    """
    Log API response metadata directly to DB.
    Supports both legacy file path and new payload_dict approach.
    If payload_dict provided, it's stored as JSON; otherwise response_payload_path is stored.
    """
    try:
        payload_json = None
        if payload_dict:
            payload_json = json.dumps(payload_dict, ensure_ascii=False)[:8000]
        
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO api_responses
                (query_id, agent_id, provider, model, attempt, response_payload_path,
                 response_code, response_redacted, actual_tokens_in, actual_tokens_out,
                 latency_ms, error_message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_id, agent_id, provider, model, attempt, response_payload_path or "",
                 response_code, response_redacted, actual_tokens_in, actual_tokens_out,
                 latency_ms, error_message[:500] if error_message else "", 
                 payload_json, time.time())
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"log_api_response error (non-fatal): {e}")


async def log_scraper_invocation(
    query_id: str,
    scraper_name: str,
    scraper_config_path: str = "",
    config_redacted: bool = True,
    start_time: float = None,
    end_time: float = None,
    chunks_returned: int = 0,
    raw_output_path: str = "",
    error_message: str = "",
    circuit_breaker_state: str = "closed",
    raw_output_dict: dict = None,
    is_compressed: bool = False,
    db_path: str = DB_PATH,
):
    """
    Log scraper invocation metadata directly to DB.
    Supports both legacy raw_output_path and new raw_output_dict approach.
    If raw_output_dict provided, it's stored as JSON; otherwise raw_output_path is stored.
    """
    if start_time is None:
        start_time = time.time()
    if end_time is None:
        end_time = time.time()
    
    duration_ms = (end_time - start_time) * 1000
    
    try:
        raw_output_json = None
        if raw_output_dict:
            raw_output_json = json.dumps(raw_output_dict, ensure_ascii=False)[:10000]
        
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO scraper_invocations
                (query_id, scraper_name, scraper_config_path, config_redacted,
                 start_time, end_time, duration_ms, chunks_returned, raw_output_path,
                 raw_output_json, is_compressed, error_message, circuit_breaker_state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_id, scraper_name, scraper_config_path or "", config_redacted,
                 start_time, end_time, duration_ms, chunks_returned, raw_output_path or "",
                 raw_output_json, is_compressed,
                 error_message[:500] if error_message else "", circuit_breaker_state,
                 time.time())
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"log_scraper_invocation error (non-fatal): {e}")


async def log_orchestrator_plan(
    query_id: str,
    reasoning: str,
    query_profile: str,
    selected_scrapers: list,
    selected_models: dict,
    fallback_used: bool = False,
    constraints_applied: str = "",
    decision_tree_path: str = "",
    plan_graph_json: str = None,
    plan_hash: str = None,
    db_path: str = DB_PATH,
):
    """
    Log orchestrator planning decisions with full graph data.
    plan_graph_json: full orchestrator plan including nodes/edges as JSON string
    plan_hash: hash of plan for future deduplication
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO orchestrator_plan
                (query_id, reasoning, query_profile, selected_scrapers, selected_models,
                 plan_graph_json, plan_hash, fallback_used, constraints_applied, 
                 decision_tree_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_id,
                 reasoning[:2000] if reasoning else "",
                 query_profile,
                 json.dumps(selected_scrapers),
                 json.dumps(selected_models),
                 plan_graph_json or "",
                 plan_hash or "",
                 fallback_used,
                 constraints_applied[:500] if constraints_applied else "",
                 decision_tree_path[:500] if decision_tree_path else "",
                 time.time())
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"log_orchestrator_plan error (non-fatal): {e}")


async def log_agent_reasoning(
    query_id: str,
    agent_id: str,
    agent_role: str,
    step_number: int,
    reasoning_text: str,
    decision_made: str = "",
    source_chunks_used: int = 0,
    confidence: float = 0.0,
    db_path: str = DB_PATH,
):
    """Log agent intermediate reasoning steps."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO agent_reasoning
                (query_id, agent_id, agent_role, step_number, reasoning_text,
                 decision_made, source_chunks_used, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_id, agent_id, agent_role, step_number,
                 reasoning_text[:2000] if reasoning_text else "",
                 decision_made[:500] if decision_made else "",
                 source_chunks_used, confidence, time.time())
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"log_agent_reasoning error (non-fatal): {e}")


async def batch_mark_logged(
    query_id: str,
    table_names: list = None,
    db_path: str = DB_PATH,
):
    """
    Mark all entries for a query as batch_logged_at (pipeline completion time).
    Called at end of pipeline when query completes successfully.
    """
    if table_names is None:
        table_names = [
            "api_requests", "api_responses", "scraper_invocations",
            "orchestrator_plan", "agent_reasoning"
        ]
    
    batch_time = time.time()
    
    try:
        async with aiosqlite.connect(db_path) as db:
            for table_name in table_names:
                try:
                    await db.execute(
                        f"UPDATE {table_name} SET batch_logged_at = ? WHERE query_id = ? AND batch_logged_at IS NULL",
                        (batch_time, query_id)
                    )
                except Exception as e:
                    logger.debug(f"batch_mark_logged for {table_name} error: {e}")
            await db.commit()
    except Exception as e:
        logger.debug(f"batch_mark_logged error (non-fatal): {e}")
