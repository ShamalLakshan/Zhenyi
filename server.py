"""
FastAPI Web Server for Zhenyi - Intelligent Research Agent
Run with: uvicorn server:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from core.events import EventBus, PipelineEvent, EventType
from core.pipeline import run
from core.key_pool import KeyPool
from core.state_store import init_db, get_recent_queries, get_thought_chain
from core.debug_store import init_debug_tables
from core.db_migration import migrate_to_latest, create_query_execution_table
from scrapers.registry import ScraperRegistry

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("core.pipeline").setLevel(logging.INFO)
logging.getLogger("server").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "zhenyi.db")
LOG_DIR = Path(os.getenv("LOG_DIR", "logs/queries"))
MAX_QUERY_LENGTH = 2000
MAX_RECENT_QUERIES = 100


def _normalize_ratio(llm_ratio: int, scraper_ratio: int) -> dict:
    """Normalize user-provided ratio values into canonical percentage form."""
    if llm_ratio < 0 or scraper_ratio < 0:
        raise ValueError("Ratio values must be non-negative")

    total = llm_ratio + scraper_ratio
    if total <= 0:
        raise ValueError("Ratio values must sum to a positive number")

    normalized_llm = round((llm_ratio / total) * 100)
    normalized_scraper = 100 - normalized_llm

    return {
        "llm_ratio": normalized_llm,
        "scraper_ratio": normalized_scraper,
        "requested_llm_ratio": llm_ratio,
        "requested_scraper_ratio": scraper_ratio,
        "ratio_total": total,
    }


def _safe_json_load(value: Optional[str], fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _build_execution_graph(scrapers: list[dict], api_calls: list[dict]) -> dict:
    nodes = [
        {"id": "orchestrator", "label": "Orchestrator", "type": "stage"},
        {"id": "triage", "label": "Triage", "type": "stage"},
        {"id": "analysis", "label": "Analysis", "type": "stage"},
        {"id": "synthesizer", "label": "Synthesis", "type": "stage"},
        {"id": "output", "label": "Output", "type": "stage"},
    ]
    edges = [
        {"from": "orchestrator", "to": "triage"},
        {"from": "triage", "to": "analysis"},
        {"from": "analysis", "to": "synthesizer"},
        {"from": "synthesizer", "to": "output"},
    ]

    scraper_seen = set()
    for scraper in scrapers:
        scraper_name = (scraper.get("scraper_name") or "unknown").lower()
        node_id = f"scraper-{scraper_name}"
        if node_id in scraper_seen:
            continue
        scraper_seen.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "label": scraper_name,
                "type": "scraper",
                "chunks": scraper.get("chunks_returned", 0),
                "duration_ms": scraper.get("duration_ms", 0),
            }
        )
        edges.append({"from": "orchestrator", "to": node_id})
        edges.append({"from": node_id, "to": "triage"})

    model_seen = set()
    for call in api_calls:
        provider = (call.get("provider") or "unknown").lower()
        model = call.get("model") or "unknown"
        role = (call.get("agent_id") or "agent").lower()
        node_id = f"model-{provider}-{model}".replace("/", "-")
        if node_id not in model_seen:
            model_seen.add(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "label": f"{provider}:{model}",
                    "type": "model",
                    "provider": provider,
                    "model": model,
                }
            )

        if role.startswith("analyst"):
            edges.append({"from": "analysis", "to": node_id})
            edges.append({"from": node_id, "to": "analysis"})
        elif role == "triage":
            edges.append({"from": "triage", "to": node_id})
            edges.append({"from": node_id, "to": "triage"})
        elif role == "synthesizer":
            edges.append({"from": "synthesizer", "to": node_id})
            edges.append({"from": node_id, "to": "synthesizer"})
        else:
            edges.append({"from": "orchestrator", "to": node_id})

    # Remove duplicate edges while preserving order.
    dedup = set()
    unique_edges = []
    for edge in edges:
        key = (edge["from"], edge["to"])
        if key in dedup:
            continue
        dedup.add(key)
        unique_edges.append(edge)

    return {"nodes": nodes, "edges": unique_edges}

# ── FastAPI Setup ────────────────────────────────────────────────────────
app = FastAPI(
    title="Zhenyi - Research Agent API",
    description="Research query execution with real-time streaming",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global State ─────────────────────────────────────────────────────────
pool: Optional[KeyPool] = None
registry: Optional[ScraperRegistry] = None
event_bus: Optional[EventBus] = None
running_queries: dict[str, asyncio.Task] = {}


# ── Pydantic Models ──────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    """Submit a research query."""
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LENGTH)
    focus_area: Optional[str] = Field(None, max_length=200)
    llm_ratio: int = Field(70, ge=0, le=100)
    scraper_ratio: int = Field(30, ge=0, le=100)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: float
    queries_running: int


# ── Startup & Shutdown ──────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Initialize database, pools, and event bus."""
    global pool, registry, event_bus

    try:
        logger.info("Starting up...")
        
        # Initialize database and run migrations
        await init_db(DB_PATH)
        await init_debug_tables(DB_PATH)
        await migrate_to_latest(DB_PATH)
        await create_query_execution_table(DB_PATH)
        logger.info("Database initialized and migrations complete")

        # Initialize key pool
        pool = KeyPool("agents.yaml")
        logger.info(f"Key pool initialized with {len(pool.pools)} providers")

        # Initialize scraper registry
        import yaml
        with open("agents.yaml", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        registry = ScraperRegistry(config.get("scrapers", {}))
        logger.info("Scraper registry initialized")

        # Initialize event bus
        event_bus = await EventBus.get_instance()
        logger.info("Event bus initialized")

        logger.info("✓ Server startup complete")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel running queries and clean up."""
    global running_queries
    
    for query_id, task in running_queries.items():
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug(f"Cancelled query {query_id}")
    
    logger.info("Server shutdown complete")


# ── Health & Status ──────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    try:
        return HealthResponse(
            status="healthy",
            timestamp=time.time(),
            queries_running=len(running_queries),
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/api/status")
async def system_status():
    """System-wide status: keys, scrapers, running queries."""
    try:
        global pool
        
        return {
            "status": "running",
            "timestamp": time.time(),
            "queries_running": len(running_queries),
            "key_pool": {
                "providers": list(pool.pools.keys()) if pool else [],
                "key_count": len(pool.pools) if pool else 0,
            },
            "scrapers": ["web", "hackernews", "wikipedia", "arxiv", "openalex"],
        }
    except Exception as e:
        logger.error(f"system_status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")


# ── Query Submission ─────────────────────────────────────────────────────
@app.post("/api/query")
async def submit_query(req: QueryRequest, background_tasks: BackgroundTasks):
    """Submit a research query for processing."""
    global pool, registry, event_bus, running_queries

    if not pool or not registry or not event_bus:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        query_text = req.query.strip()
        if not query_text:
            raise ValueError("Query cannot be empty or whitespace")

        ratio_controls = _normalize_ratio(req.llm_ratio, req.scraper_ratio)

        query_id = str(uuid.uuid4())[:8]

        async def run_pipeline():
            """Background task to run the research pipeline."""
            try:
                # Emit start event
                await event_bus.publish(
                    PipelineEvent(
                        EventType.QUERY_STARTED,
                        query_id,
                        {
                            "query": query_text,
                            "focus_area": req.focus_area or "",
                            "ratio_controls": ratio_controls,
                        },
                    )
                )

                logger.info(f"[{query_id}] Running pipeline for: {query_text[:50]}...")

                # Run the pipeline with the same query_id and event_bus for real-time events
                result = await run(
                    query_text,
                    pool,
                    registry,
                    query_id=query_id,
                    event_bus=event_bus,
                    query_controls={
                        "focus_area": req.focus_area or "",
                        "ratio_controls": ratio_controls,
                    },
                )
                
                # Emit completion event
                await event_bus.publish(
                    PipelineEvent(
                        EventType.QUERY_DONE,
                        query_id,
                        {
                            "query_id": query_id,
                            "answer": result.get("answer", ""),
                            "confidence": result.get("confidence", 0.0),
                            "profile": result.get("profile", ""),
                            "duration_ms": result.get("duration_ms", 0),
                            "sources": result.get("sources", []),
                            "plan": result.get("plan", {}),
                            "ratio_controls": ratio_controls,
                        },
                    )
                )

                logger.info(f"[{query_id}] Pipeline complete")

            except asyncio.CancelledError:
                logger.info(f"[{query_id}] Query cancelled")
                await event_bus.publish(
                    PipelineEvent(
                        EventType.QUERY_ERROR, query_id, {"error": "Cancelled by user"}
                    )
                )
            except Exception as e:
                logger.error(f"[{query_id}] Pipeline error: {e}")
                await event_bus.publish(
                    PipelineEvent(EventType.QUERY_ERROR, query_id, {"error": str(e)})
                )
            finally:
                # Cleanup
                running_queries.pop(query_id, None)
                await event_bus.clear_query_subscriptions(query_id)

        # Create background task
        task = asyncio.create_task(run_pipeline())
        running_queries[query_id] = task

        logger.info(f"[{query_id}] Query submitted: {query_text[:50]}...")

        return JSONResponse(
            status_code=202,
            content={"query_id": query_id, "status": "processing"},
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"submit_query error: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit query")


# ── Query History & Management ──────────────────────────────────────────
@app.get("/api/queries")
async def list_queries(
    limit: int = Query(100, ge=1, le=MAX_RECENT_QUERIES),
    offset: int = Query(0, ge=0),
):
    """List recent queries with pagination."""
    try:
        queries = await get_recent_queries(limit=limit + offset, db_path=DB_PATH)
        return {
            "queries": queries[offset : offset + limit],
            "total": len(queries),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"list_queries error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list queries")


@app.get("/api/queries/{query_id}")
async def get_query(query_id: str):
    """Get full query result with plan and answer."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM queries WHERE query_id = ?", (query_id,)
            )
            row = await cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Query not found")

            result = dict(row)
            result["plan"] = _safe_json_load(result.get("plan_json"), {})
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_query error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get query")


@app.get("/api/history")
async def get_history(limit: int = Query(50, ge=1, le=200)):
    """Get historical queries (alias for list_queries with limit)."""
    try:
        queries = await get_recent_queries(limit=limit, db_path=DB_PATH)
        return {"queries": queries, "count": len(queries)}
    except Exception as e:
        logger.error(f"get_history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get history")


@app.delete("/api/queries/{query_id}")
async def delete_query(query_id: str):
    """Delete query and associated logs."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM queries WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM thought_chain WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM chunks WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM agent_outputs WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM orchestrator_plan WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM api_requests WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM api_responses WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM scraper_invocations WHERE query_id = ?", (query_id,))
            await db.execute("DELETE FROM agent_reasoning WHERE query_id = ?", (query_id,))
            await db.commit()

        log_path = LOG_DIR / query_id
        if log_path.exists():
            shutil.rmtree(log_path)

        return {"status": "deleted", "query_id": query_id}
    except Exception as e:
        logger.error(f"delete_query error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete query")


# ── Logs & Debug Info ───────────────────────────────────────────────────
@app.get("/api/logs/{query_id}")
async def get_logs(query_id: str):
    """Get thought chain (logs) for a query."""
    try:
        chain = await get_thought_chain(query_id, db_path=DB_PATH)
        return {"query_id": query_id, "logs": chain}
    except Exception as e:
        logger.error(f"get_logs error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get logs")


@app.get("/api/debug/{query_id}")
async def get_debug(query_id: str, stage: Optional[str] = None):
    """Get debug info for a query. Maps stage names to log data."""
    try:
        log_path = LOG_DIR / query_id
        if not log_path.exists():
            raise HTTPException(status_code=404, detail="Logs not found")

        if stage:
            # Map stage names to log directories/files
            stage_mapping = {
                'orchestrator': 'orchestrator_plan.json',
                'scrapers': 'scraper_outputs',
                'triage': 'agent_reasoning',  # Triage agent logs
                'analysts': 'agent_reasoning',
                'synthesizer': 'agent_reasoning',
                'output': None  # Not a log type
            }
            
            log_ref = stage_mapping.get(stage)
            if log_ref is None:
                # Get query result for output panel
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute(
                        "SELECT * FROM queries WHERE query_id = ?",
                        (query_id,),
                    )
                    row = await cursor.fetchone()
                    if not row:
                        raise HTTPException(status_code=404, detail="Query not found")
                    query_data = dict(row)
                    query_data["plan"] = _safe_json_load(query_data.get("plan_json"), {})
                    return {"query_id": query_id, "stage": stage, "data": query_data}
            
            log_target = log_path / log_ref
            
            # Handle single file
            if log_target.suffix == '.json':
                if not log_target.exists():
                    return {"query_id": query_id, "stage": stage, "data": {}}
                try:
                    data = json.loads(log_target.read_text())
                    return {"query_id": query_id, "stage": stage, "data": data}
                except Exception as e:
                    logger.debug(f"Could not parse {log_ref}: {e}")
                    return {"query_id": query_id, "stage": stage, "data": {"raw": log_target.read_text()}}
            
            # Handle directory
            if log_target.exists() and log_target.is_dir():
                files = {}
                for f in log_target.glob("*.json"):
                    try:
                        files[f.stem] = json.loads(f.read_text())
                    except Exception as e:
                        logger.debug(f"Could not parse {f.name}: {e}")
                        files[f.stem] = {"error": str(e)}
                
                if not files:
                    return {"query_id": query_id, "stage": stage, "data": {"message": "No data found"}}
                
                return {"query_id": query_id, "stage": stage, "data": files}
            
            # Not found
            return {"query_id": query_id, "stage": stage, "data": {"message": "Stage data not available"}}
        else:
            # Get all stages
            result = {
                "query_id": query_id,
                "stages": {}
            }
            
            # List what's available
            if (log_path / "orchestrator_plan.json").exists():
                result["stages"]["orchestrator"] = True
            
            for subdir in ['scraper_outputs', 'agent_reasoning', 'api_requests', 'api_responses']:
                if (log_path / subdir).exists():
                    result["stages"][subdir] = True
            
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_debug error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get debug info")


# ── Query Management ────────────────────────────────────────────────────
@app.post("/api/cancel/{query_id}")
async def cancel_query(query_id: str):
    """Cancel a running query."""
    if query_id not in running_queries:
        raise HTTPException(status_code=404, detail="Query not running or not found")

    try:
        task = running_queries[query_id]
        task.cancel()
        logger.info(f"Cancelled query {query_id}")
        return {"status": "cancelled", "query_id": query_id}
    except Exception as e:
        logger.error(f"cancel_query error: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel query")


# ── Database Debug Endpoints (DB-only logging) ──────────────────────────
@app.get("/api/logs/{query_id}/graph")
async def get_orchestrator_graph(query_id: str):
    """
    Get orchestrator plan graph (nodes/edges) from database.
    Used by frontend to render pipeline visualization.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT plan_graph_json FROM orchestrator_plan WHERE query_id = ?",
                (query_id,)
            )
            row = await cursor.fetchone()
            
            if not row or not row["plan_graph_json"]:
                # Fallback: return empty graph
                return {
                    "query_id": query_id,
                    "nodes": [],
                    "edges": [],
                    "message": "No graph data found"
                }
            
            # Parse and return the graph
            graph_data = json.loads(row["plan_graph_json"])
            return {"query_id": query_id, **graph_data}
    except Exception as e:
        logger.error(f"get_orchestrator_graph error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get graph")


@app.get("/api/debug/{query_id}/full")
async def get_full_debug_info(query_id: str):
    """
    Get complete debug information for a query from database.
    Includes orchestrator plan, API requests/responses, scraper logs, agent reasoning.
    """
    try:
        result = {
            "query_id": query_id,
            "orchestrator_plan": None,
            "api_requests": [],
            "api_responses": [],
            "scraper_invocations": [],
            "agent_reasoning": [],
        }
        
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Get orchestrator plan
            cursor = await db.execute(
                "SELECT * FROM orchestrator_plan WHERE query_id = ?",
                (query_id,)
            )
            row = await cursor.fetchone()
            if row:
                plan = dict(row)
                # Parse JSON fields
                if plan.get("plan_graph_json"):
                    plan["plan_graph"] = json.loads(plan["plan_graph_json"])
                result["orchestrator_plan"] = plan
            
            # Get API requests
            cursor = await db.execute(
                "SELECT * FROM api_requests WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                req = dict(row)
                if req.get("payload_json"):
                    req["payload"] = json.loads(req["payload_json"])
                result["api_requests"].append(req)
            
            # Get API responses
            cursor = await db.execute(
                "SELECT * FROM api_responses WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                resp = dict(row)
                if resp.get("payload_json"):
                    resp["payload"] = json.loads(resp["payload_json"])
                result["api_responses"].append(resp)
            
            # Get scraper invocations
            cursor = await db.execute(
                "SELECT * FROM scraper_invocations WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                scraper = dict(row)
                if scraper.get("raw_output_json"):
                    scraper["raw_output"] = json.loads(scraper["raw_output_json"])
                result["scraper_invocations"].append(scraper)
            
            # Get agent reasoning
            cursor = await db.execute(
                "SELECT * FROM agent_reasoning WHERE query_id = ? ORDER BY step_number ASC",
                (query_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                reasoning = dict(row)
                result["agent_reasoning"].append(reasoning)
        
        return result
    except Exception as e:
        logger.error(f"get_full_debug_info error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get full debug info")


@app.get("/api/queries/{query_id}/execution")
async def get_query_execution(query_id: str):
    """Get normalized execution details for graph + result analytics views."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM queries WHERE query_id = ?",
                (query_id,),
            )
            query_row = await cursor.fetchone()
            if not query_row:
                raise HTTPException(status_code=404, detail="Query not found")
            query_data = dict(query_row)

            cursor = await db.execute(
                "SELECT * FROM orchestrator_plan WHERE query_id = ?",
                (query_id,),
            )
            plan_row = await cursor.fetchone()
            orchestrator_plan = dict(plan_row) if plan_row else None

            cursor = await db.execute(
                "SELECT * FROM api_responses WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,),
            )
            api_rows = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute(
                "SELECT * FROM scraper_invocations WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,),
            )
            scraper_rows = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute(
                "SELECT source, url, content, relevance_score, created_at FROM chunks WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,),
            )
            chunk_rows = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute(
                "SELECT step, note, created_at FROM thought_chain WHERE query_id = ? ORDER BY created_at ASC",
                (query_id,),
            )
            thought_rows = [dict(r) for r in await cursor.fetchall()]

        plan_data = _safe_json_load(query_data.get("plan_json"), {})
        stage_details = plan_data.get("stage_details", {}) if isinstance(plan_data, dict) else {}
        total_tokens = sum((row.get("actual_tokens_in") or 0) + (row.get("actual_tokens_out") or 0) for row in api_rows)
        provider_usage = defaultdict(lambda: {
            "provider": "",
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": 0.0,
        })
        for row in api_rows:
            provider = row.get("provider") or "unknown"
            provider_usage[provider]["provider"] = provider
            provider_usage[provider]["calls"] += 1
            provider_usage[provider]["tokens_in"] += row.get("actual_tokens_in") or 0
            provider_usage[provider]["tokens_out"] += row.get("actual_tokens_out") or 0
            provider_usage[provider]["latency_ms"] += row.get("latency_ms") or 0

        provider_breakdown = []
        for usage in provider_usage.values():
            provider_tokens = usage["tokens_in"] + usage["tokens_out"]
            usage["usage_pct"] = round((provider_tokens / total_tokens) * 100, 2) if total_tokens else 0.0
            provider_breakdown.append(usage)
        provider_breakdown.sort(key=lambda x: x["usage_pct"], reverse=True)

        total_scraper_chunks = sum(row.get("chunks_returned") or 0 for row in scraper_rows)
        scraper_map = defaultdict(lambda: {"name": "", "calls": 0, "chunks": 0, "duration_ms": 0.0})
        for row in scraper_rows:
            name = row.get("scraper_name") or "unknown"
            scraper_map[name]["name"] = name
            scraper_map[name]["calls"] += 1
            scraper_map[name]["chunks"] += row.get("chunks_returned") or 0
            scraper_map[name]["duration_ms"] += row.get("duration_ms") or 0

        scraper_breakdown = []
        for usage in scraper_map.values():
            usage["usage_pct"] = round((usage["chunks"] / total_scraper_chunks) * 100, 2) if total_scraper_chunks else 0.0
            scraper_breakdown.append(usage)
        scraper_breakdown.sort(key=lambda x: x["usage_pct"], reverse=True)

        stage_metrics = {
            "orchestrator_ms": sum((r.get("latency_ms") or 0) for r in api_rows if (r.get("agent_id") or "") == "orchestrator"),
            "triage_ms": sum((r.get("latency_ms") or 0) for r in api_rows if (r.get("agent_id") or "") == "triage"),
            "analysis_ms": sum((r.get("latency_ms") or 0) for r in api_rows if (r.get("agent_id") or "").startswith("analyst_")),
            "synthesis_ms": sum((r.get("latency_ms") or 0) for r in api_rows if (r.get("agent_id") or "") == "synthesizer"),
            "scraping_ms": sum((r.get("duration_ms") or 0) for r in scraper_rows),
        }
        stage_total_ms = sum(stage_metrics.values())
        stage_breakdown = [
            {
                "name": "Plan",
                "value": round(stage_metrics["orchestrator_ms"], 2),
                "usage_pct": round((stage_metrics["orchestrator_ms"] / stage_total_ms) * 100, 2) if stage_total_ms else 0.0,
            },
            {
                "name": "Crawl",
                "value": round(stage_metrics["scraping_ms"], 2),
                "usage_pct": round((stage_metrics["scraping_ms"] / stage_total_ms) * 100, 2) if stage_total_ms else 0.0,
            },
            {
                "name": "Triage",
                "value": round(stage_metrics["triage_ms"], 2),
                "usage_pct": round((stage_metrics["triage_ms"] / stage_total_ms) * 100, 2) if stage_total_ms else 0.0,
            },
            {
                "name": "Analyst",
                "value": round(stage_metrics["analysis_ms"], 2),
                "usage_pct": round((stage_metrics["analysis_ms"] / stage_total_ms) * 100, 2) if stage_total_ms else 0.0,
            },
            {
                "name": "Synth",
                "value": round(stage_metrics["synthesis_ms"], 2),
                "usage_pct": round((stage_metrics["synthesis_ms"] / stage_total_ms) * 100, 2) if stage_total_ms else 0.0,
            },
        ]

        graph = _build_execution_graph(scraper_rows, api_rows)
        if orchestrator_plan and orchestrator_plan.get("plan_graph_json"):
            persisted_graph = _safe_json_load(orchestrator_plan.get("plan_graph_json"), {})
            if persisted_graph.get("nodes"):
                graph["nodes"] = persisted_graph["nodes"]
            if persisted_graph.get("edges"):
                graph["edges"] = persisted_graph["edges"]

        def _build_filtered_chunk(chunk: dict, idx: int) -> dict:
            source = chunk.get("source", "unknown") or "unknown"
            is_llm = str(source).lower().startswith("llm_")
            return {
                "source": source,
                "url": chunk.get("url", ""),
                "content": chunk.get("content", ""),
                "text": chunk.get("content", ""),
                "title": f"{source} chunk #{idx + 1}",
                "score": chunk.get("relevance_score", 0),
                "relevance_score": chunk.get("relevance_score", 0),
                "stage": "filtered",
                "is_llm_generated": is_llm,
                "source_kind": "llm" if is_llm else "scraper",
                "policy_block": False,
                "provenance": {
                    "source_id": source,
                    "source_kind": "llm" if is_llm else "scraper",
                    "provider_name": source.replace("llm_", "") if is_llm else "",
                    "scraper_name": source if not is_llm else "",
                    "original_response_path": "",
                },
            }

        filtered_chunks = [_build_filtered_chunk(chunk, idx) for idx, chunk in enumerate(chunk_rows)]

        stage_api_calls: dict[str, list[dict]] = {
            "orchestrator": [],
            "triage": [],
            "analysts": [],
            "synthesizer": [],
        }
        for call in api_rows:
            agent_id = (call.get("agent_id") or "").lower()
            compact_call = {
                "agent_id": call.get("agent_id", ""),
                "provider": call.get("provider", ""),
                "model": call.get("model", ""),
                "latency_ms": call.get("latency_ms", 0),
                "tokens_in": call.get("actual_tokens_in", 0),
                "tokens_out": call.get("actual_tokens_out", 0),
                "response_code": call.get("response_code", 0),
                "created_at": call.get("created_at"),
                "response_payload_path": call.get("response_payload_path", ""),
            }
            if agent_id == "orchestrator":
                stage_api_calls["orchestrator"].append(compact_call)
            elif agent_id == "triage":
                stage_api_calls["triage"].append(compact_call)
            elif agent_id.startswith("analyst"):
                stage_api_calls["analysts"].append(compact_call)
            elif agent_id == "synthesizer":
                stage_api_calls["synthesizer"].append(compact_call)

        scraper_stage_calls = []
        scraper_node_details: dict[str, dict] = {}
        for row in scraper_rows:
            scraper_name = (row.get("scraper_name") or "unknown").lower()
            compact_scraper = {
                "scraper_name": scraper_name,
                "duration_ms": row.get("duration_ms", 0),
                "chunks_returned": row.get("chunks_returned", 0),
                "circuit_breaker_state": row.get("circuit_breaker_state", ""),
                "error_message": row.get("error_message", ""),
                "raw_output_path": row.get("raw_output_path", ""),
                "created_at": row.get("created_at"),
            }
            scraper_stage_calls.append(compact_scraper)
            node_id = f"scraper-{scraper_name}"
            scraper_node_details[node_id] = {
                "id": node_id,
                "name": scraper_name,
                "status": "done",
                "latency_ms": row.get("duration_ms", 0),
                "metrics": {
                    "chunks_returned": row.get("chunks_returned", 0),
                    "duration_ms": row.get("duration_ms", 0),
                    "circuit_breaker_state": row.get("circuit_breaker_state", ""),
                },
                "logs": [
                    f"Scraper {scraper_name} returned {row.get('chunks_returned', 0)} chunks",
                ],
                "api_calls": [],
                "scraper_calls": [compact_scraper],
                "chunks": {
                    "raw": [],
                    "scored": [],
                    "filtered": [
                        c for c in filtered_chunks if str(c.get("source", "")).lower() == scraper_name
                    ],
                },
            }

        execution_stage_details = {
            "orchestrator": {
                "id": "orchestrator",
                "name": "Orchestrator",
                "status": "done",
                "latency_ms": round(stage_metrics["orchestrator_ms"], 2),
                "metrics": {
                    "profile": query_data.get("profile", "research"),
                    "reasoning_available": bool(orchestrator_plan and orchestrator_plan.get("reasoning")),
                },
                "logs": [
                    (orchestrator_plan or {}).get("reasoning", "Planning complete"),
                ],
                "api_calls": stage_api_calls["orchestrator"],
                "scraper_calls": [],
                "chunks": {
                    "raw": stage_details.get("orchestrator", {}).get("chunks", {}).get("raw", []),
                    "scored": stage_details.get("orchestrator", {}).get("chunks", {}).get("scored", []),
                    "filtered": stage_details.get("orchestrator", {}).get("chunks", {}).get("filtered", []),
                },
            },
            "scraping": {
                "id": "scraping",
                "name": "Scraping",
                "status": "done",
                "latency_ms": round(stage_metrics["scraping_ms"], 2),
                "metrics": {
                    "scraper_calls": len(scraper_rows),
                    "raw_chunk_count": sum(row.get("chunks_returned") or 0 for row in scraper_rows),
                },
                "logs": [f"Executed {len(scraper_rows)} scraper calls"],
                "api_calls": [],
                "scraper_calls": scraper_stage_calls,
                "chunks": {
                    "raw": stage_details.get("scraping", {}).get("chunks", {}).get("raw", []),
                    "scored": stage_details.get("scraping", {}).get("chunks", {}).get("scored", []),
                    "filtered": stage_details.get("scraping", {}).get("chunks", {}).get("filtered", []),
                },
            },
            "triage": {
                "id": "triage",
                "name": "Triage",
                "status": "done",
                "latency_ms": round(stage_metrics["triage_ms"], 2),
                "metrics": {
                    "filtered_count": len(filtered_chunks),
                    "ratio_delta": (plan_data.get("execution_metrics", {}) or {}).get("ratio_delta", {}),
                },
                "logs": ["Scored and filtered chunks"],
                "api_calls": stage_api_calls["triage"],
                "scraper_calls": [],
                "chunks": {
                    "raw": stage_details.get("triage", {}).get("chunks", {}).get("raw", []),
                    "scored": stage_details.get("triage", {}).get("chunks", {}).get("scored", []),
                    "filtered": filtered_chunks,
                },
            },
            "analysts": {
                "id": "analysts",
                "name": "Analysts",
                "status": "done",
                "latency_ms": round(stage_metrics["analysis_ms"], 2),
                "metrics": {
                    "api_calls": len(stage_api_calls["analysts"]),
                    "thought_steps": len([t for t in thought_rows if (t.get("step") or "").startswith("anal")]),
                },
                "logs": ["Parallel analysis completed"],
                "api_calls": stage_api_calls["analysts"],
                "scraper_calls": [],
                "chunks": {
                    "raw": stage_details.get("analysts", {}).get("chunks", {}).get("raw", []),
                    "scored": stage_details.get("analysts", {}).get("chunks", {}).get("scored", []),
                    "filtered": filtered_chunks,
                },
            },
            "synthesizer": {
                "id": "synthesizer",
                "name": "Synthesizer",
                "status": "done",
                "latency_ms": round(stage_metrics["synthesis_ms"], 2),
                "metrics": {
                    "answer_length": len(query_data.get("answer") or ""),
                    "confidence": query_data.get("confidence", 0),
                },
                "logs": ["Final answer assembled"],
                "api_calls": stage_api_calls["synthesizer"],
                "scraper_calls": [],
                "chunks": {
                    "raw": stage_details.get("synthesizer", {}).get("chunks", {}).get("raw", []),
                    "scored": stage_details.get("synthesizer", {}).get("chunks", {}).get("scored", []),
                    "filtered": filtered_chunks,
                },
            },
            "output": {
                "id": "output",
                "name": "Output",
                "status": "done",
                "latency_ms": 0,
                "metrics": {
                    "source_count": len([chunk.get("url") for chunk in chunk_rows if chunk.get("url")]),
                    "duration_ms": query_data.get("duration_ms", 0),
                },
                "logs": ["Execution response generated"],
                "api_calls": [],
                "scraper_calls": [],
                "chunks": {
                    "raw": [],
                    "scored": [],
                    "filtered": filtered_chunks,
                },
            },
        }
        execution_stage_details.update(scraper_node_details)

        return {
            "query_id": query_id,
            "summary": {
                "query": query_data.get("query_text", ""),
                "profile": query_data.get("profile", "research"),
                "confidence": query_data.get("confidence", 0.0),
                "duration_ms": query_data.get("duration_ms", 0.0),
                "plan": plan_data,
                "controls": plan_data.get("query_controls", {}),
                "execution_metrics": plan_data.get("execution_metrics", {}),
                "sources": [
                    chunk.get("url")
                    for chunk in chunk_rows
                    if chunk.get("url")
                ][:20],
            },
            "graph": graph,
            "usage": {
                "providers": provider_breakdown,
                "scrapers": scraper_breakdown,
                "total_tokens": total_tokens,
            },
            "stages": {
                "breakdown": stage_breakdown,
                "metrics": stage_metrics,
                "thought_chain": thought_rows,
                "details": execution_stage_details,
            },
            "chunks": {
                "raw": stage_details.get("scraping", {}).get("chunks", {}).get("raw", []),
                "scored": stage_details.get("triage", {}).get("chunks", {}).get("scored", []),
                "filtered": filtered_chunks,
                "counts": {
                    "filtered": len(chunk_rows),
                    "raw": sum(row.get("chunks_returned") or 0 for row in scraper_rows),
                    "scored": len(chunk_rows),
                },
            },
            "debug": {
                "api_calls": len(api_rows),
                "scraper_calls": len(scraper_rows),
                "orchestrator_plan": orchestrator_plan,
                "api_calls_detail": api_rows,
                "scraper_calls_detail": scraper_rows,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_query_execution error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get query execution")


@app.get("/api/keys/status")
async def get_keys_status():
    """
    Get current status of all API keys in the key pool.
    Shows ready/cooling/exhausted states for debugging.
    """
    try:
        global pool
        if not pool:
            raise HTTPException(status_code=503, detail="Key pool not initialized")
        
        status = {}
        for provider, keys in pool.pools.items():
            status[provider] = [k.to_dict() for k in keys]
        
        return {
            "providers": list(pool.pools.keys()),
            "key_status": status,
            "timestamp": time.time(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_keys_status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get key status")


# ── WebSocket Endpoints ─────────────────────────────────────────────────
@app.websocket("/ws/query/{query_id}")
async def websocket_query_stream(websocket: WebSocket, query_id: str):
    """Real-time event stream for a specific query."""
    global event_bus

    if not event_bus:
        await websocket.close(code=1011, reason="Event bus not initialized")
        return

    await websocket.accept()
    logger.info(f"[WS] Connected for {query_id}")

    # Callback to send events via websocket
    async def on_event(event: PipelineEvent):
        try:
            await websocket.send_json(event.to_dict())
            logger.debug(f"[WS] Sent {event.event_type} to {query_id}")
        except Exception as e:
            logger.debug(f"[WS] Send error for {query_id}: {e}")

    try:
        # Subscribe to this query's events (will replay history)
        await event_bus.subscribe(query_id, on_event)
        logger.info(f"[WS] Subscribed {query_id}")

        # Keep connection alive indefinitely
        while True:
            try:
                # This will block until message or timeout
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                logger.debug(f"[WS] Received from {query_id}: {msg[:50]}")
            except asyncio.TimeoutError:
                # Send keep-alive ping
                try:
                    await websocket.send_json({"type": "ping", "ts": time.time()})
                    logger.debug(f"[WS] Ping sent to {query_id}")
                except Exception as e:
                    logger.debug(f"[WS] Ping failed for {query_id}: {e}")
                    break
            except Exception as e:
                logger.debug(f"[WS] Receive error for {query_id}: {e}")
                break

    except WebSocketDisconnect:
        logger.info(f"[WS] Disconnected {query_id}")
    except asyncio.CancelledError:
        logger.info(f"[WS] Cancelled {query_id}")
    except Exception as e:
        logger.error(f"[WS] Exception {query_id}: {e}", exc_info=True)
    finally:
        try:
            await event_bus.unsubscribe(query_id, on_event)
            logger.info(f"[WS] Unsubscribed {query_id}")
        except Exception as e:
            logger.debug(f"[WS] Unsubscribe error: {e}")


# ── Main ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
