"""
Pipeline
────────
Orchestrates the full research flow:
  1. Orchestrator plans  → decides roles and scrapers
  2. Scrapers run        → raw chunks collected
  3. Triage              → irrelevant chunks dropped
  4. Analysts            → parallel analysis of chunk slices
  5. Synthesizer         → final answer assembled

Each stage is isolated:
  - A stage failure returns a partial/empty result, not a crash
  - The pipeline always returns a valid result dict
  - All steps are logged to the thought chain

Simple factual queries short-circuit after planning:
  no scraping, no triage, one direct analyst call.
"""

import asyncio
import logging
import time
import uuid
import json
from pathlib import Path
from contextlib import asynccontextmanager

from core.key_pool import KeyPool
from core import state_store
from core import debug_store
from core.redaction import redact_request_payload, redact_response_payload, safe_json_dumps
from core.events import EventBus, PipelineEvent, EventType
from scrapers.registry import ScraperRegistry
from agents.orchestrator import OrchestratorAgent
from agents.triage import TriageAgent
from agents.analyst import AnalystAgent
from agents.synthesizer import SynthesizerAgent

logger = logging.getLogger(__name__)

# Global log context (thread-local would be better in production)
_current_log_context = None


class LogContext:
    """
    Logging context for a query execution.
    Collects all logs during a query run (scrapers, models, reasoning).
    On successful completion, batches all logs to DB and writes files.
    OnFailure, minimal error info is logged.
    """
    
    def __init__(self, query_id: str, query_text: str):
        self.query_id = query_id
        self.query_text = query_text
        self.log_root = Path("logs/queries") / query_id
        self.log_root.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        (self.log_root / "api_requests").mkdir(exist_ok=True)
        (self.log_root / "api_responses").mkdir(exist_ok=True)
        (self.log_root / "scraper_outputs").mkdir(exist_ok=True)
        (self.log_root / "agent_reasoning").mkdir(exist_ok=True)
        
        self.is_success = False
        logger.debug(f"[{query_id}] Log context initialized at {self.log_root}")
    
    async def log_api_request(
        self, agent_id: str, provider: str, model: str, attempt: int,
        request_dict: dict, estimated_tokens: int = 0
    ) -> str:
        """
        Log full API request payload (redacted).
        Returns path to stored file.
        """
        try:
            redacted = redact_request_payload(request_dict)
            filename = f"{provider}_{model}_{attempt}.json"
            filepath = self.log_root / "api_requests" / filename
            
            with open(filepath, "w") as f:
                json.dump({
                    "agent_id": agent_id,
                    "provider": provider,
                    "model": model,
                    "attempt": attempt,
                    "timestamp": time.time(),
                    "payload": redacted
                }, f, indent=2)
            
            # Also log to DB (deferred batching)
            await debug_store.log_api_request(
                self.query_id, agent_id, provider, model, attempt,
                str(filepath.relative_to(Path.cwd())),
                headers_redacted=True, body_redacted=True,
                estimated_tokens=estimated_tokens
            )
            
            return str(filepath)
        except Exception as e:
            logger.debug(f"log_api_request error (non-fatal): {e}")
            return None
    
    async def log_api_response(
        self, agent_id: str, provider: str, model: str, attempt: int,
        response_dict: dict = None, response_code: int = 200,
        actual_tokens_in: int = 0, actual_tokens_out: int = 0,
        latency_ms: float = 0, error_message: str = None
    ) -> str:
        """
        Log full API response payload (redacted).
        Returns path to stored file.
        """
        try:
            if response_dict:
                redacted = redact_response_payload(response_dict)
                filename = f"{provider}_{model}_{attempt}.json"
                filepath = self.log_root / "api_responses" / filename
                
                with open(filepath, "w") as f:
                    json.dump({
                        "agent_id": agent_id,
                        "provider": provider,
                        "model": model,
                        "attempt": attempt,
                        "timestamp": time.time(),
                        "response_code": response_code,
                        "payload": redacted
                    }, f, indent=2)
            else:
                filepath = None
            
            # Also log to DB (deferred batching)
            await debug_store.log_api_response(
                self.query_id, agent_id, provider, model, attempt,
                str(filepath.relative_to(Path.cwd())) if filepath else None,
                response_code=response_code, response_redacted=True,
                actual_tokens_in=actual_tokens_in, actual_tokens_out=actual_tokens_out,
                latency_ms=latency_ms, error_message=error_message or ""
            )
            
            return str(filepath) if filepath else None
        except Exception as e:
            logger.debug(f"log_api_response error (non-fatal): {e}")
            return None
    
    async def log_scraper(
        self, scraper_name: str, config: dict, start_time: float,
        end_time: float, chunks_returned: int = 0,
        raw_output: dict = None, error_message: str = None,
        circuit_state: str = "closed"
    ):
        """Log scraper invocation and output."""
        try:
            from core.redaction import redact_json_payload
            
            # Save config (redacted)
            config_redacted = redact_json_payload(config)
            config_file = self.log_root / "scraper_outputs" / f"{scraper_name}_config.json"
            with open(config_file, "w") as f:
                json.dump(config_redacted, f, indent=2)
            
            # Save raw output if provided
            output_file = None
            if raw_output:
                output_file = self.log_root / "scraper_outputs" / f"{scraper_name}_output.json"
                with open(output_file, "w") as f:
                    json.dump(raw_output if isinstance(raw_output, dict) else {"output": raw_output}, f, indent=2)
            
            # Log to DB
            await debug_store.log_scraper_invocation(
                self.query_id, scraper_name,
                str(config_file.relative_to(Path.cwd())),
                config_redacted=True,
                start_time=start_time, end_time=end_time,
                chunks_returned=chunks_returned,
                raw_output_path=str(output_file.relative_to(Path.cwd())) if output_file else "",
                error_message=error_message or "",
                circuit_breaker_state=circuit_state
            )
        except Exception as e:
            logger.debug(f"log_scraper error (non-fatal): {e}")
    
    async def log_orchestrator_plan(
        self, reasoning: str, profile: str, scrapers: list,
        models: dict, fallback_used: bool = False, constraints: str = ""
    ):
        """Log orchestrator planning decisions."""
        try:
            plan_file = self.log_root / "orchestrator_plan.json"
            with open(plan_file, "w") as f:
                json.dump({
                    "reasoning": reasoning,
                    "profile": profile,
                    "scrapers": scrapers,
                    "models": models,
                    "fallback_used": fallback_used,
                    "constraints": constraints,
                    "timestamp": time.time()
                }, f, indent=2)
            
            await debug_store.log_orchestrator_plan(
                self.query_id, reasoning, profile, scrapers, models,
                fallback_used=fallback_used, constraints_applied=constraints,
                decision_tree_path=str(plan_file.relative_to(Path.cwd()))
            )
        except Exception as e:
            logger.debug(f"log_orchestrator_plan error (non-fatal): {e}")
    
    async def log_agent_reasoning(
        self, agent_id: str, agent_role: str, step: int,
        reasoning: str, decision: str = "", chunks_used: int = 0, confidence: float = 0.0
    ):
        """Log agent reasoning step."""
        try:
            await debug_store.log_agent_reasoning(
                self.query_id, agent_id, agent_role, step,
                reasoning, decision_made=decision,
                source_chunks_used=chunks_used, confidence=confidence
            )
        except Exception as e:
            logger.debug(f"log_agent_reasoning error (non-fatal): {e}")
    
    async def batch_mark_success(self):
        """Mark all logs as batch-logged (called on query success)."""
        self.is_success = True
        try:
            await debug_store.batch_mark_logged(self.query_id)
            logger.debug(f"[{self.query_id}] Logs batch-marked as complete")
        except Exception as e:
            logger.debug(f"batch_mark_success error (non-fatal): {e}")


@asynccontextmanager
async def create_log_context(query_id: str, query_text: str):
    """Context manager for query logging. Usage: async with create_log_context(...) as ctx:"""
    global _current_log_context
    ctx = LogContext(query_id, query_text)
    old_ctx = _current_log_context
    _current_log_context = ctx
    try:
        yield ctx
    finally:
        _current_log_context = old_ctx


def get_current_log_context() -> LogContext:
    """Get the current logging context (if any)."""
    return _current_log_context


def _make_agent_from_role(role_cfg: dict, role_name: str, pool: KeyPool):
    """
    Instantiate the correct agent class for a role config dict.
    Returns an AnalystAgent for analyst roles, otherwise the specific class.
    """
    provider = role_cfg.get("provider", "groq")
    model = role_cfg.get("model", "")
    if not model:
        # Try to get default from pool config
        p_cfg = pool.config.get("providers", {}).get(provider, {})
        model = p_cfg.get("models", {}).get("default", "")

    if "analyst" in role_name:
        return AnalystAgent(role_name, pool, provider=provider, model=model)
    elif role_name == "triage":
        return TriageAgent(pool, provider=provider, model=model)
    elif role_name == "synthesizer":
        return SynthesizerAgent(pool, provider=provider, model=model)
    else:
        # Generic — return as AnalystAgent (can call + parse JSON)
        return AnalystAgent(role_name, pool, provider=provider, model=model)


async def run(query: str, pool: KeyPool, registry: ScraperRegistry, query_id: str = None, event_bus: EventBus = None) -> dict:
    """
    Execute the full research pipeline for a query.
    Always returns a dict with: query_id, profile, answer, confidence, sources, plan.
    
    Logs all operations (scrapers, models, reasoning) if logging is enabled.
    On successful completion, all logs are batch-written to DB and files.
    
    Args:
        query: The research query string
        pool: KeyPool for API credentials
        registry: ScraperRegistry for available scrapers
        query_id: Optional query ID; if not provided, generates a new one
        event_bus: Optional EventBus for emitting real-time events
    """
    if query_id is None:
        query_id = str(uuid.uuid4())[:8]
    t_start = time.time()
    
    # Get event bus if not provided
    if event_bus is None:
        try:
            event_bus = await EventBus.get_instance()
        except Exception as e:
            logger.debug(f"Could not get event bus: {e}")
            event_bus = None
    
    # Initialize debug tables on first run
    try:
        await debug_store.init_debug_tables()
    except Exception as e:
        logger.debug(f"Debug tables init (non-fatal): {e}")

    # Wrap entire pipeline in logging context for batching
    async with create_log_context(query_id, query) as log_ctx:
        try:
            logger.info(f"[{query_id}] Starting pipeline: {query[:80]}")
            await state_store.log_thought(query_id, "start", f"query: {query}")

            # ── Stage 1: Orchestrator Planning ────────────────────────────────────────
            print(f"\n[{query_id}] {query[:70]}")
            print("  [1/5] Planning...")
            
            # Emit orchestrator start event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.ORCHESTRATOR_STARTED,
                        query_id,
                        {"query": query, "query_id": query_id}
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit ORCHESTRATOR_STARTED: {e}")

            try:
                orchestrator = OrchestratorAgent(pool)
                plan = await orchestrator.plan(query, query_id, log_ctx)
            except Exception as e:
                logger.error(f"[{query_id}] Orchestrator failed: {e}")
                plan = {
                    "profile": "research",
                    "scrapers": ["hackernews"],
                    "analyst_count": 1,
                    "roles": {},
                    "reasoning": f"Orchestrator failed: {e}",
                }

            profile     = plan.get("profile", "research")
            roles       = plan.get("roles", {})
            scrapers    = plan.get("scrapers", ["hackernews"])
            reasoning   = plan.get("reasoning", "")

            print(f"       profile={profile} | scrapers={scrapers}")
            print(f"       reason: {reasoning}")

            # ── Simple factual short-circuit ──────────────────────────────────────────
            if profile == "simple_factual":
                print("  [2-4/5] Skipped (simple factual)")
                analyst_cfg = roles.get("analyst_0", {})
                if not analyst_cfg:
                    analyst_cfg = _pick_fallback_role(pool, "analysis")

                agent = _make_agent_from_role(analyst_cfg, "analyst_0", pool)
                raw = await agent.call(
                    f"Answer this question directly and accurately:\n\n{query}",
                    query_id=query_id,
                )
                answer = raw or "Could not generate an answer."
                duration = (time.time() - t_start) * 1000
                await state_store.save_query_result(
                    query_id, query, profile, plan, answer, 0.85, duration
                )
                await state_store.log_thought(query_id, "done", "simple_factual direct answer")
                await log_ctx.batch_mark_success()
                return {
                    "query_id": query_id,
                    "profile": profile,
                    "answer": answer,
                    "confidence": 0.85,
                    "sources": [],
                    "plan": plan,
                    "duration_ms": duration,
                }

            # ── Stage 2: Scraping ─────────────────────────────────────────────────────
            print(f"  [2/5] Scraping {scrapers}...")
            await state_store.log_thought(query_id, "scrape_start", str(scrapers))
            
            # Emit scraper started event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.SCRAPER_STARTED,
                        query_id,
                        {"scrapers": scrapers, "query": query}
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit SCRAPER_STARTED: {e}")

            try:
                chunks = await registry.run(scrapers, query, log_ctx=log_ctx, query_id=query_id)
            except Exception as e:
                logger.error(f"[{query_id}] Scraper registry error: {e}")
                chunks = []

            max_chunks = pool.get_threshold("max_chunks", 20)
            chunks = chunks[:max_chunks]
            print(f"         got {len(chunks)} raw chunks")
            await state_store.log_thought(query_id, "scraped", f"{len(chunks)} chunks")
            
            # Emit chunks collected event with detailed chunk data
            if event_bus:
                try:
                    chunk_summary = [
                        {
                            "index": i,
                            "source": c.get("source", "unknown"),
                            "title": c.get("title", "")[:100],
                            "url": c.get("url", ""),
                            "length": len(c.get("content", ""))
                        }
                        for i, c in enumerate(chunks)
                    ]
                    await event_bus.publish(PipelineEvent(
                        EventType.CHUNKS_COLLECTED,
                        query_id,
                        {
                            "total_chunks": len(chunks),
                            "chunks": chunk_summary,
                            "raw_chunks_full": chunks  # Include full data for persistence
                        }
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit CHUNKS_COLLECTED: {e}")

            # ── Stage 2b: LLM-Generated Chunks (augment scraper data) ──────────────────
            # Call LLM providers to generate diverse perspectives as chunks
            # These will be triaged alongside scraper data
            llm_chunks = []
            if roles.get("analyst_0"):  # If we have analyst roles, get their perspectives
                print(f"  [2b/5] Gathering LLM perspectives...")
                llm_perspective_tasks = []
                
                # Get up to 2 analyst perspectives as additional chunks
                for i in range(min(2, plan.get("analyst_count", 1))):
                    analyst_key = f"analyst_{i}"
                    analyst_cfg = roles.get(analyst_key)
                    if analyst_cfg:
                        llm_perspective_tasks.append(
                            _get_llm_perspective_as_chunk(
                                query, analyst_cfg, pool, query_id, log_ctx, analyst_key
                            )
                        )
                
                if llm_perspective_tasks:
                    perspectives = await asyncio.gather(*llm_perspective_tasks, return_exceptions=True)
                    for perspective in perspectives:
                        if isinstance(perspective, dict) and perspective.get("content"):
                            llm_chunks.append(perspective)
                    
                    if llm_chunks:
                        print(f"         got {len(llm_chunks)} LLM-generated chunks")
            
            # Combine scraper chunks + LLM chunks for triage
            all_chunks = chunks + llm_chunks
            
            if not all_chunks:
                await state_store.log_thought(query_id, "done", "no data from scrapers or llm")
                await log_ctx.batch_mark_success()
                if event_bus:
                    try:
                        await event_bus.publish(PipelineEvent(
                            EventType.SCRAPER_DONE,
                            query_id,
                            {"chunks_collected": 0, "status": "no_data"}
                        ))
                    except Exception as e:
                        logger.debug(f"Could not emit SCRAPER_DONE: {e}")
                return _empty_result(query_id, profile, plan,
                                     "No data found from any scraper or LLM.", t_start)

            # ── Stage 3: Triage ───────────────────────────────────────────────────────
            print("  [3/5] Triaging...")
            
            # Emit triage started event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.TRIAGE_STARTED,
                        query_id,
                        {"total_chunks": len(chunks), "threshold": threshold if threshold else 6}
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit TRIAGE_STARTED: {e}")
            
            triage_cfg = roles.get("triage")
            if not triage_cfg:
                triage_cfg = _pick_fallback_role(pool, "speed")

            threshold = pool.get_threshold("relevance_min_score", 6)
            triage_mode = plan.get("triage_mode", "hybrid")  # Get mode from plan

            try:
                triage = _make_agent_from_role(triage_cfg, "triage", pool)
                scored = await triage.score_chunks(
                    query, all_chunks, threshold, 
                    query_id=query_id,
                    mode=triage_mode  # Pass triage mode to agent
                )
            except Exception as e:
                logger.error(f"[{query_id}] Triage error: {e}")
                scored = chunks  # pass all through on triage failure
            
            # Emit chunks scored event (if scoring happened)
            if event_bus and scored != all_chunks:
                try:
                    scored_summary = [
                        {
                            "index": i,
                            "source": c.get("source", "unknown"),
                            "title": c.get("title", "")[:100],
                            "score": c.get("relevance_score", 0),
                            "url": c.get("url", "")
                        }
                        for i, c in enumerate(scored)
                    ]
                    await event_bus.publish(PipelineEvent(
                        EventType.CHUNKS_SCORED,
                        query_id,
                        {
                            "scored_chunks": scored_summary,
                            "total_scored": len(scored),
                            "threshold": threshold
                        }
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit CHUNKS_SCORED: {e}")

            # Safety net — if triage filtered everything out, keep top chunks
            if not scored:
                logger.warning(f"[{query_id}] Triage removed all chunks — keeping top 3")
                scored = all_chunks[:3]

            await state_store.save_chunks(query_id, scored)
            await state_store.log_thought(query_id, "triage", f"kept {len(scored)}/{len(all_chunks)}")
            print(f"         kept {len(scored)}/{len(all_chunks)}")
            
            # Emit chunks filtered event
            if event_bus:
                try:
                    filtered_summary = [
                        {
                            "index": i,
                            "source": c.get("source", "unknown"),
                            "title": c.get("title", "")[:100],
                            "url": c.get("url", "")
                        }
                        for i, c in enumerate(scored)
                    ]
                    await event_bus.publish(PipelineEvent(
                        EventType.CHUNKS_FILTERED,
                        query_id,
                        {
                            "filtered_chunks": filtered_summary,
                            "kept": len(scored),
                            "total": len(chunks),
                            "dropped": len(chunks) - len(scored)
                        }
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit CHUNKS_FILTERED: {e}")
            
            # Emit triage done event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.TRIAGE_DONE,
                        query_id,
                        {"chunks_remaining": len(scored), "chunks_dropped": len(chunks) - len(scored)}
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit TRIAGE_DONE: {e}")

            # ── Stage 4: Parallel Analysis ────────────────────────────────────────────
            analyst_keys = sorted(
                [k for k in roles if k.startswith("analyst_")]
            )
            if not analyst_keys:
                analyst_keys = ["analyst_0"]

            analyst_count = len(analyst_keys)
            print(f"  [4/5] Running {analyst_count} analyst(s) in parallel...")
            await state_store.log_thought(query_id, "analyse_start", f"{analyst_count} analysts")
            
            # Emit analyst start event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.ANALYST_START,
                        query_id,
                        {"analyst_count": analyst_count, "total_chunks": len(scored)}
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit ANALYST_START: {e}")

            # Distribute chunks evenly across analysts
            chunk_slices = _split_chunks(scored, analyst_count)
            
            # Emit analyst chunk slices
            if event_bus:
                try:
                    for i, key in enumerate(analyst_keys):
                        chunk_slice = chunk_slices[i] if i < len(chunk_slices) else scored
                        slice_summary = [
                            {
                                "index": j,
                                "source": c.get("source", "unknown"),
                                "title": c.get("title", "")[:80]
                            }
                            for j, c in enumerate(chunk_slice)
                        ]
                        await event_bus.publish(PipelineEvent(
                            EventType.ANALYST_CHUNK_SLICE,
                            query_id,
                            {
                                "analyst_id": key,
                                "chunk_count": len(chunk_slice),
                                "chunks": slice_summary
                            }
                        ))
                except Exception as e:
                    logger.debug(f"Could not emit ANALYST_CHUNK_SLICE: {e}")

            analyst_tasks = []
            for i, key in enumerate(analyst_keys):
                role_cfg = roles.get(key)
                if not role_cfg:
                    role_cfg = _pick_fallback_role(pool, "analysis")
                agent = _make_agent_from_role(role_cfg, key, pool)
                chunk_slice = chunk_slices[i] if i < len(chunk_slices) else scored
                analyst_tasks.append(agent.analyse(query, chunk_slice, query_id, log_ctx))

            raw_results = await asyncio.gather(*analyst_tasks, return_exceptions=True)

            analyst_outputs = []
            for i, result in enumerate(raw_results):
                if isinstance(result, Exception):
                    logger.error(f"[{query_id}] analyst_{i} raised: {result}")
                elif isinstance(result, dict):
                    analyst_outputs.append(result)

            print(f"         {len(analyst_outputs)}/{analyst_count} analysts returned")
            await state_store.log_thought(
                query_id, "analysed", f"{len(analyst_outputs)} outputs"
            )
            
            # Emit analyst done event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.ANALYST_DONE,
                        query_id,
                        {
                            "successful_analysts": len(analyst_outputs),
                            "total_analysts": analyst_count,
                            "total_findings": sum(len(o.get("key_findings", [])) for o in analyst_outputs)
                        }
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit ANALYST_DONE: {e}")

            if not analyst_outputs:
                await log_ctx.batch_mark_success()
                return _empty_result(
                    query_id, profile, plan,
                    "All analysts failed to return results.", t_start
                )

            # ── Stage 5: Synthesis ────────────────────────────────────────────────────
            print("  [5/5] Synthesizing...")
            
            # Emit synthesizer started event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.SYNTHESIZER_STARTED,
                        query_id,
                        {
                            "analyst_outputs": len(analyst_outputs),
                            "total_findings": sum(len(o.get("key_findings", [])) for o in analyst_outputs)
                        }
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit SYNTHESIZER_STARTED: {e}")
            
            synth_cfg = roles.get("synthesizer")
            if not synth_cfg:
                synth_cfg = _pick_fallback_role(pool, "synthesis")

            try:
                synth = _make_agent_from_role(synth_cfg, "synthesizer", pool)
                final = await synth.synthesize(query, analyst_outputs, query_id, log_ctx)
            except Exception as e:
                logger.error(f"[{query_id}] Synthesizer error: {e}")
                # Build answer from raw findings as fallback
                findings = [
                    f for out in analyst_outputs
                    for f in out.get("key_findings", [])
                ]
                final = {
                    "answer": "\n".join(findings) or "Synthesis failed.",
                    "confidence": 0.3,
                }
            
            # Emit synthesizer done event
            if event_bus:
                try:
                    await event_bus.publish(PipelineEvent(
                        EventType.SYNTHESIZER_DONE,
                        query_id,
                        {
                            "answer_length": len(final.get("answer", "")),
                            "confidence": final.get("confidence", 0),
                            "has_sources": len([c.get("url", "") for c in scored if c.get("url")]) > 0
                        }
                    ))
                except Exception as e:
                    logger.debug(f"Could not emit SYNTHESIZER_DONE: {e}")

            sources = list({c.get("url", "") for c in scored if c.get("url")})
            duration = (time.time() - t_start) * 1000

            await state_store.log_thought(
                query_id, "done",
                f"confidence={final['confidence']:.2f} duration={duration:.0f}ms"
            )
            await state_store.save_query_result(
                query_id, query, profile, plan,
                final["answer"], final["confidence"], duration
            )

            # Mark all logs as successfully batch-logged
            await log_ctx.batch_mark_success()

            return {
                "query_id":   query_id,
                "profile":    profile,
                "answer":     final["answer"],
                "confidence": final["confidence"],
                "sources":    sources[:10],
                "plan":       plan,
                "duration_ms": duration,
            }
        except Exception as e:
            logger.error(f"[{query_id}] Pipeline error: {e}")
            await log_ctx.batch_mark_success()  # Still mark partial logs
            raise  # Re-raise to caller


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_llm_perspective_as_chunk(
    query: str,
    analyst_cfg: dict,
    pool: KeyPool,
    query_id: str,
    log_ctx,
    analyst_id: str
) -> dict:
    """
    Call an LLM analyst and convert their response into a chunk for triage.
    Returns a dict with structure: {content, source, title, url, llm_provider, llm_model}
    """
    try:
        agent = _make_agent_from_role(analyst_cfg, analyst_id, pool)
        provider = analyst_cfg.get("provider", "unknown")
        model = analyst_cfg.get("model", "unknown")
        
        prompt = f"""Provide a focused, concise perspective on this query in 2-3 sentences:

Query: {query}

Give your most important insight or analysis."""
        
        response = await agent.call(prompt, query_id=query_id)
        
        if response:
            return {
                "content": response,
                "source": f"llm_{provider}",
                "title": f"LLM Perspective ({provider})",
                "url": "",
                "llm_provider": provider,
                "llm_model": model,
                "is_llm_generated": True,
            }
    except Exception as e:
        logger.debug(f"[{query_id}] LLM perspective error ({analyst_id}): {e}")
    
    return {}


def _split_chunks(chunks: list, n: int) -> list[list]:
    """Split chunks into n roughly equal slices."""
    if n <= 1 or not chunks:
        return [chunks]
    size = max(1, len(chunks) // n)
    slices = []
    for i in range(n):
        start = i * size
        end = start + size if i < n - 1 else len(chunks)
        slices.append(chunks[start:end])
    return slices


def _pick_fallback_role(pool: KeyPool, need: str) -> dict:
    """
    Pick any available provider as a fallback when the plan is missing a role.
    'need' is a hint: 'speed', 'analysis', 'synthesis'.
    """
    strength_map = {
        "speed":     ["speed", "general"],
        "analysis":  ["reasoning", "analysis", "general"],
        "synthesis": ["synthesis", "rag", "general"],
    }
    snapshot = pool.get_capabilities_snapshot()
    preferred = strength_map.get(need, ["general"])

    for provider, info in snapshot.items():
        if any(s in info.get("strengths", []) for s in preferred):
            models = info.get("models", {})
            model = models.get("default") or (list(models.values())[0] if models else "")
            return {"provider": provider, "model": model}

    # Last resort: first available provider
    if snapshot:
        provider = next(iter(snapshot))
        info = snapshot[provider]
        models = info.get("models", {})
        model = models.get("default") or (list(models.values())[0] if models else "")
        return {"provider": provider, "model": model}

    return {"provider": "groq", "model": "llama-3.1-8b-instant"}


def _empty_result(
    query_id: str, profile: str, plan: dict, reason: str, t_start: float
) -> dict:
    duration = (time.time() - t_start) * 1000
    return {
        "query_id":    query_id,
        "profile":     profile,
        "answer":      reason,
        "confidence":  0.0,
        "sources":     [],
        "plan":        plan,
        "duration_ms": duration,
    }
