"""
Debug API
─────────
Query interface for retrieving comprehensive query logs and debugging information.
Enables query-focused, model-focused, scraper-focused, and error-focused analysis.

Usage:
  audit = await get_query_audit("abc123")
  models = await get_model_invocations("abc123", model="llama-3.3-70b")
  scrapers = await get_scraper_calls("abc123", scraper_name="web")
  errors = await get_errors_and_retries("abc123")
  report = await export_query_debug_report("abc123", "/tmp/report.json")
"""

import aiosqlite
import json
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)
DB_PATH = "zhenyi.db"


async def get_query_audit(query_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Get complete execution trace for a query.
    Returns: orchestrator plan + all scrapers + all model calls + agent reasoning.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # Get query metadata
            query_row = await db.execute_one(
                "SELECT query_text, profile, answer, confidence, duration_ms FROM queries WHERE query_id = ?",
                (query_id,)
            )
            
            # Get orchestrator plan
            plan_row = await db.execute_one(
                "SELECT reasoning, query_profile, selected_scrapers, selected_models, fallback_used FROM orchestrator_plan WHERE query_id = ?",
                (query_id,)
            )
            
            # Get all scraper calls
            scraper_rows = await db.execute_all(
                """SELECT scraper_name, duration_ms, chunks_returned, error_message, 
                          scraper_config_path FROM scraper_invocations WHERE query_id = ? 
                   ORDER BY created_at""",
                (query_id,)
            )
            
            # Get all model invocations
            api_req_rows = await db.execute_all(
                """SELECT agent_id, provider, model, attempt, request_payload_path, 
                          estimated_tokens FROM api_requests WHERE query_id = ? 
                   ORDER BY created_at""",
                (query_id,)
            )
            
            api_resp_rows = await db.execute_all(
                """SELECT agent_id, provider, model, attempt, response_payload_path, 
                          response_code, latency_ms, actual_tokens_in, actual_tokens_out,
                          error_message FROM api_responses WHERE query_id = ?
                   ORDER BY created_at""",
                (query_id,)
            )
            
            # Get agent reasoning
            reasoning_rows = await db.execute_all(
                """SELECT agent_id, agent_role, step_number, reasoning_text, decision_made,
                          confidence FROM agent_reasoning WHERE query_id = ?
                   ORDER BY agent_id, step_number""",
                (query_id,)
            )
            
            return {
                "query_id": query_id,
                "query": {
                    "text": query_row[0] if query_row else None,
                    "profile": query_row[1] if query_row else None,
                    "answer": query_row[2] if query_row else None,
                    "confidence": query_row[3] if query_row else None,
                    "duration_ms": query_row[4] if query_row else None,
                },
                "orchestrator": {
                    "reasoning": plan_row[0] if plan_row else None,
                    "profile": plan_row[1] if plan_row else None,
                    "scrapers": json.loads(plan_row[2]) if plan_row and plan_row[2] else [],
                    "models": json.loads(plan_row[3]) if plan_row and plan_row[3] else {},
                    "fallback_used": plan_row[4] if plan_row else False,
                } if plan_row else None,
                "scrapers": [
                    {
                        "name": row[0],
                        "duration_ms": row[1],
                        "chunks_returned": row[2],
                        "error": row[3],
                        "config_file": row[4],
                    } for row in scraper_rows
                ],
                "model_invocations": [
                    {
                        "agent": api_req[0],
                        "provider": api_req[1],
                        "model": api_req[2],
                        "attempt": api_req[3],
                        "request_payload_file": api_req[4],
                        "estimated_tokens": api_req[5],
                        "response": {
                            "code": api_resp[5],
                            "latency_ms": api_resp[6],
                            "tokens_in": api_resp[7],
                            "tokens_out": api_resp[8],
                            "error": api_resp[9],
                            "payload_file": api_resp[4],
                        }
                    } for api_req, api_resp in zip(api_req_rows, api_resp_rows)
                    if api_req and api_resp and api_req[3] == api_resp[3] and api_req[1] == api_resp[1]
                ],
                "agent_reasoning": [
                    {
                        "agent": row[0],
                        "role": row[1],
                        "step": row[2],
                        "reasoning": row[3],
                        "decision": row[4],
                        "confidence": row[5],
                    } for row in reasoning_rows
                ],
            }
    except Exception as e:
        logger.error(f"get_query_audit error: {e}")
        return {"error": str(e)}


async def get_scraper_calls(
    query_id: str,
    scraper_name: Optional[str] = None,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    """Get all scraper invocations for a query, optionally filtered by scraper name."""
    try:
        async with aiosqlite.connect(db_path) as db:
            if scraper_name:
                rows = await db.execute_all(
                    """SELECT scraper_name, start_time, end_time, duration_ms, chunks_returned,
                              error_message, circuit_breaker_state, scraper_config_path,
                              raw_output_path FROM scraper_invocations
                       WHERE query_id = ? AND scraper_name = ?
                       ORDER BY created_at""",
                    (query_id, scraper_name)
                )
            else:
                rows = await db.execute_all(
                    """SELECT scraper_name, start_time, end_time, duration_ms, chunks_returned,
                              error_message, circuit_breaker_state, scraper_config_path,
                              raw_output_path FROM scraper_invocations
                       WHERE query_id = ?
                       ORDER BY created_at""",
                    (query_id,)
                )
            
            return [
                {
                    "scraper": row[0],
                    "start_time": row[1],
                    "end_time": row[2],
                    "duration_ms": row[3],
                    "chunks_returned": row[4],
                    "error": row[5],
                    "circuit_state": row[6],
                    "config_file": row[7],
                    "output_file": row[8],
                } for row in rows
            ]
    except Exception as e:
        logger.error(f"get_scraper_calls error: {e}")
        return []


async def get_model_invocations(
    query_id: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    """Get all model invocations for a query, optionally filtered by provider/model."""
    try:
        async with aiosqlite.connect(db_path) as db:
            if provider and model:
                rows = await db.execute_all(
                    """SELECT req.agent_id, req.provider, req.model, req.attempt,
                              req.request_payload_path, req.estimated_tokens,
                              resp.response_payload_path, resp.response_code, resp.latency_ms,
                              resp.actual_tokens_in, resp.actual_tokens_out, resp.error_message
                       FROM api_requests req
                       LEFT JOIN api_responses resp ON req.query_id = resp.query_id 
                         AND req.agent_id = resp.agent_id AND req.attempt = resp.attempt
                       WHERE req.query_id = ? AND req.provider = ? AND req.model = ?
                       ORDER BY req.created_at""",
                    (query_id, provider, model)
                )
            elif provider:
                rows = await db.execute_all(
                    """SELECT req.agent_id, req.provider, req.model, req.attempt,
                              req.request_payload_path, req.estimated_tokens,
                              resp.response_payload_path, resp.response_code, resp.latency_ms,
                              resp.actual_tokens_in, resp.actual_tokens_out, resp.error_message
                       FROM api_requests req
                       LEFT JOIN api_responses resp ON req.query_id = resp.query_id 
                         AND req.agent_id = resp.agent_id AND req.attempt = resp.attempt
                       WHERE req.query_id = ? AND req.provider = ?
                       ORDER BY req.created_at""",
                    (query_id, provider)
                )
            else:
                rows = await db.execute_all(
                    """SELECT req.agent_id, req.provider, req.model, req.attempt,
                              req.request_payload_path, req.estimated_tokens,
                              resp.response_payload_path, resp.response_code, resp.latency_ms,
                              resp.actual_tokens_in, resp.actual_tokens_out, resp.error_message
                       FROM api_requests req
                       LEFT JOIN api_responses resp ON req.query_id = resp.query_id 
                         AND req.agent_id = resp.agent_id AND req.attempt = resp.attempt
                       WHERE req.query_id = ?
                       ORDER BY req.created_at""",
                    (query_id,)
                )
            
            return [
                {
                    "agent": row[0],
                    "provider": row[1],
                    "model": row[2],
                    "attempt": row[3],
                    "request": {
                        "payload_file": row[4],
                        "estimated_tokens": row[5],
                    },
                    "response": {
                        "payload_file": row[6],
                        "code": row[7],
                        "latency_ms": row[8],
                        "tokens_in": row[9],
                        "tokens_out": row[10],
                        "error": row[11],
                    }
                } for row in rows
            ]
    except Exception as e:
        logger.error(f"get_model_invocations error: {e}")
        return []


async def get_errors_and_retries(query_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Get all failures and retry attempts for a query."""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Model failures
            model_errors = await db.execute_all(
                """SELECT agent_id, provider, model, attempt, latency_ms, error_message
                   FROM api_responses
                   WHERE query_id = ? AND error_message IS NOT NULL AND error_message != ''
                   ORDER BY created_at""",
                (query_id,)
            )
            
            # Scraper failures
            scraper_errors = await db.execute_all(
                """SELECT scraper_name, duration_ms, error_message, circuit_breaker_state
                   FROM scraper_invocations
                   WHERE query_id = ? AND error_message IS NOT NULL AND error_message != ''
                   ORDER BY created_at""",
                (query_id,)
            )
            
            # Get retry attempts (multiple attempts by same agent)
            retries = await db.execute_all(
                """SELECT agent_id, provider, model, COUNT(*) as attempts,
                          GROUP_CONCAT(CAST(attempt AS TEXT), ',') as attempt_nums
                   FROM api_requests
                   WHERE query_id = ?
                   GROUP BY agent_id, provider, model
                   HAVING COUNT(*) > 1
                   ORDER BY agent_id""",
                (query_id,)
            )
            
            return {
                "query_id": query_id,
                "model_failures": [
                    {
                        "agent": row[0],
                        "provider": row[1],
                        "model": row[2],
                        "attempt": row[3],
                        "latency_ms": row[4],
                        "error": row[5],
                    } for row in model_errors
                ],
                "scraper_failures": [
                    {
                        "scraper": row[0],
                        "duration_ms": row[1],
                        "error": row[2],
                        "circuit_state": row[3],
                    } for row in scraper_errors
                ],
                "retry_attempts": [
                    {
                        "agent": row[0],
                        "provider": row[1],
                        "model": row[2],
                        "total_attempts": row[3],
                        "attempt_nums": [int(x) for x in row[4].split(',')],
                    } for row in retries
                ]
            }
    except Exception as e:
        logger.error(f"get_errors_and_retries error: {e}")
        return {"error": str(e)}


async def export_query_debug_report(
    query_id: str,
    output_path: str,
    db_path: str = DB_PATH
) -> bool:
    """
    Export comprehensive debug report as JSON.
    Includes: audit, scraper calls, model invocations, errors.
    """
    try:
        audit = await get_query_audit(query_id, db_path)
        scrapers = await get_scraper_calls(query_id, db_path=db_path)
        models = await get_model_invocations(query_id, db_path=db_path)
        errors = await get_errors_and_retries(query_id, db_path=db_path)
        
        report = {
            "query_id": query_id,
            "exported_at": __import__("time").time(),
            "audit": audit,
            "scrapers": scrapers,
            "model_invocations": models,
            "errors_and_retries": errors,
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Debug report exported to {output_path}")
        return True
    except Exception as e:
        logger.error(f"export_query_debug_report error: {e}")
        return False
