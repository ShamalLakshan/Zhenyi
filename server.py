"""
FastAPI Web Server for LLM Research Council
Run with: uvicorn server:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
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
DB_PATH = os.getenv("DB_PATH", "council.db")
LOG_DIR = Path(os.getenv("LOG_DIR", "logs/queries"))
MAX_QUERY_LENGTH = 2000
MAX_RECENT_QUERIES = 100

# ── FastAPI Setup ────────────────────────────────────────────────────────
app = FastAPI(
    title="LLM Research Council API",
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
        
        # Initialize database
        await init_db(DB_PATH)
        await init_debug_tables(DB_PATH)
        logger.info("Database initialized")

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
            timestamp=datetime.utcnow().timestamp(),
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
            "timestamp": datetime.utcnow().timestamp(),
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

        query_id = str(uuid.uuid4())[:8]

        async def run_pipeline():
            """Background task to run the research pipeline."""
            try:
                # Emit start event
                await event_bus.publish(
                    PipelineEvent(
                        EventType.QUERY_STARTED,
                        query_id,
                        {"query": query_text, "focus_area": req.focus_area or ""},
                    )
                )

                logger.info(f"[{query_id}] Running pipeline for: {query_text[:50]}...")

                # Run the pipeline
                result = await run(query_text, pool, registry)
                
                # Emit completion event
                await event_bus.publish(
                    PipelineEvent(
                        EventType.QUERY_DONE,
                        query_id,
                        {
                            "answer": result.get("answer", ""),
                            "confidence": result.get("confidence", 0.0),
                            "profile": result.get("profile", ""),
                            "duration_ms": result.get("duration_ms", 0),
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

            return dict(row)
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
            await db.execute("DELETE FROM thoughts WHERE query_id = ?", (query_id,))
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
                from core.state_store import get_query
                result = await get_query(query_id)
                if not result:
                    raise HTTPException(status_code=404, detail="Query not found")
                return {"query_id": query_id, "stage": stage, "data": result}
            
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
