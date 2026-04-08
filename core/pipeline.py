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

from core.key_pool import KeyPool
from core import state_store
from scrapers.registry import ScraperRegistry
from agents.orchestrator import OrchestratorAgent
from agents.triage import TriageAgent
from agents.analyst import AnalystAgent
from agents.synthesizer import SynthesizerAgent

logger = logging.getLogger(__name__)


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


async def run(query: str, pool: KeyPool, registry: ScraperRegistry) -> dict:
    """
    Execute the full research pipeline for a query.
    Always returns a dict with: query_id, profile, answer, confidence, sources, plan.
    """
    query_id = str(uuid.uuid4())[:8]
    t_start = time.time()

    logger.info(f"[{query_id}] Starting pipeline: {query[:80]}")
    await state_store.log_thought(query_id, "start", f"query: {query}")

    # ── Stage 1: Orchestrator Planning ────────────────────────────────────────
    print(f"\n[{query_id}] {query[:70]}")
    print("  [1/5] Planning...")

    try:
        orchestrator = OrchestratorAgent(pool)
        plan = await orchestrator.plan(query, query_id)
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

    try:
        chunks = await registry.run(scrapers, query)
    except Exception as e:
        logger.error(f"[{query_id}] Scraper registry error: {e}")
        chunks = []

    max_chunks = pool.get_threshold("max_chunks", 20)
    chunks = chunks[:max_chunks]
    print(f"         got {len(chunks)} raw chunks")
    await state_store.log_thought(query_id, "scraped", f"{len(chunks)} chunks")

    if not chunks:
        await state_store.log_thought(query_id, "done", "no data from scrapers")
        return _empty_result(query_id, profile, plan,
                             "No data found from any scraper.", t_start)

    # ── Stage 3: Triage ───────────────────────────────────────────────────────
    print("  [3/5] Triaging...")
    triage_cfg = roles.get("triage")
    if not triage_cfg:
        triage_cfg = _pick_fallback_role(pool, "speed")

    threshold = pool.get_threshold("relevance_min_score", 6)

    try:
        triage = _make_agent_from_role(triage_cfg, "triage", pool)
        scored = await triage.score_chunks(query, chunks, threshold, query_id)
    except Exception as e:
        logger.error(f"[{query_id}] Triage error: {e}")
        scored = chunks  # pass all through on triage failure

    # Safety net — if triage filtered everything out, keep top chunks
    if not scored:
        logger.warning(f"[{query_id}] Triage removed all chunks — keeping top 3")
        scored = chunks[:3]

    await state_store.save_chunks(query_id, scored)
    await state_store.log_thought(query_id, "triage", f"kept {len(scored)}/{len(chunks)}")
    print(f"         kept {len(scored)}/{len(chunks)}")

    # ── Stage 4: Parallel Analysis ────────────────────────────────────────────
    analyst_keys = sorted(
        [k for k in roles if k.startswith("analyst_")]
    )
    if not analyst_keys:
        analyst_keys = ["analyst_0"]

    analyst_count = len(analyst_keys)
    print(f"  [4/5] Running {analyst_count} analyst(s) in parallel...")
    await state_store.log_thought(query_id, "analyse_start", f"{analyst_count} analysts")

    # Distribute chunks evenly across analysts
    chunk_slices = _split_chunks(scored, analyst_count)

    analyst_tasks = []
    for i, key in enumerate(analyst_keys):
        role_cfg = roles.get(key)
        if not role_cfg:
            role_cfg = _pick_fallback_role(pool, "analysis")
        agent = _make_agent_from_role(role_cfg, key, pool)
        chunk_slice = chunk_slices[i] if i < len(chunk_slices) else scored
        analyst_tasks.append(agent.analyse(query, chunk_slice, query_id))

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

    if not analyst_outputs:
        return _empty_result(
            query_id, profile, plan,
            "All analysts failed to return results.", t_start
        )

    # ── Stage 5: Synthesis ────────────────────────────────────────────────────
    print("  [5/5] Synthesizing...")
    synth_cfg = roles.get("synthesizer")
    if not synth_cfg:
        synth_cfg = _pick_fallback_role(pool, "synthesis")

    try:
        synth = _make_agent_from_role(synth_cfg, "synthesizer", pool)
        final = await synth.synthesize(query, analyst_outputs, query_id)
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

    return {
        "query_id":   query_id,
        "profile":    profile,
        "answer":     final["answer"],
        "confidence": final["confidence"],
        "sources":    sources[:10],
        "plan":       plan,
        "duration_ms": duration,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

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
