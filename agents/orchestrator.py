"""
Orchestrator Agent
──────────────────
Always uses Gemini. Given the user query and a live snapshot of available
providers, produces a complete execution plan: which scrapers to run, which
provider/model to assign to each role, and why.

Error handling:
- 429 from Gemini → extracts retry_delay from error, marks key in cooldown,
  immediately falls back to a safe plan (no waiting, no crash)
- Any other error → fallback plan from available providers
- Empty snapshot → fallback plan

The fallback plan is always valid and runnable without any LLM call.
"""

import asyncio
import json
import logging
import re
from typing import Optional

import google.generativeai as genai

from core.key_pool import KeyPool
from core import state_store
from core.exceptions import NoAvailableKeysError

logger = logging.getLogger(__name__)

AVAILABLE_SCRAPERS = ["hackernews", "reddit", "web"]


def _extract_retry_delay(error_str: str) -> float:
    """
    Parse the retry_delay seconds from a Gemini 429 error string.
    Returns 65.0 as a safe default if not found.
    """
    match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', error_str)
    if match:
        return float(match.group(1)) + 2.0
    match2 = re.search(r'retry in\s+([\d.]+)s', error_str)
    if match2:
        return float(match2.group(1)) + 2.0
    return 65.0


class OrchestratorAgent:

    def __init__(self, pool: KeyPool):
        self.pool = pool

    async def plan(self, query: str, query_id: str) -> dict:
        """
        Produce a full execution plan for this query.
        Returns a dict with: profile, scrapers, analyst_count, roles, reasoning.
        Never raises — falls back to a safe plan on any error.
        """
        try:
            api_key, model, key_state = self.pool.get_orchestrator_key()
        except NoAvailableKeysError:
            logger.error("No orchestrator keys available — using fallback plan")
            plan = self._fallback_plan()
            await state_store.log_thought(query_id, "orchestrator", "fallback: no keys")
            return plan

        snapshot = self.pool.get_capabilities_snapshot()
        if not snapshot:
            logger.error("No providers available in snapshot — using fallback plan")
            plan = self._fallback_plan()
            await state_store.log_thought(query_id, "orchestrator", "fallback: empty snapshot")
            return plan

        prompt = self._build_prompt(query, snapshot)

        try:
            genai.configure(api_key=api_key)
            gmodel = genai.GenerativeModel(model)
            resp = await asyncio.to_thread(gmodel.generate_content, prompt)
            raw = resp.text.strip()
            key_state.record_usage(estimated_tokens=800)

        except Exception as e:
            error_str = str(e)
            is_rate_limit = any(
                x in error_str.lower()
                for x in ["429", "quota", "rate limit", "too many requests", "exceeded"]
            )
            if is_rate_limit:
                delay = _extract_retry_delay(error_str)
                key_state.set_cooldown(delay)
                logger.warning(
                    f"Orchestrator 429 — key {key_state.env_var} cooling for {delay:.0f}s. "
                    f"Falling back to non-LLM plan."
                )
            else:
                key_state.record_error(is_rate_limit=False)
                logger.error(f"Orchestrator API call failed: {e}")

            plan = self._fallback_plan(snapshot)
            await state_store.log_thought(
                query_id, "orchestrator",
                f"fallback: {'rate_limit' if is_rate_limit else str(e)[:80]}"
            )
            return plan

        plan = self._parse_plan(raw, snapshot)
        plan = self._validate_and_fix_plan(plan, snapshot)

        await state_store.log_thought(
            query_id, "orchestrator_plan",
            f"profile={plan['profile']} scrapers={plan['scrapers']} "
            f"analysts={plan['analyst_count']} | {plan.get('reasoning', '')}"
        )
        return plan

    def _build_prompt(self, query: str, snapshot: dict) -> str:
        return f"""You are the orchestrator of a multi-LLM research council.
Analyse the user query and produce a JSON execution plan.

USER QUERY:
{query}

AVAILABLE PROVIDERS (live state — only use providers listed here):
{json.dumps(snapshot, indent=2)}

AVAILABLE SCRAPERS: {AVAILABLE_SCRAPERS}

PLANNING RULES:
Profile:
  simple_factual  → stable facts, definitions, history. scrapers: []
  current_factual → recent news, current status. scrapers: 1-2
  research        → multiple sources needed. scrapers: 2-3
  deep_research   → complex multi-domain. scrapers: all

Role assignment:
  triage      → fastest provider (high daily_remaining + speed strength)
  analyst     → best reasoning provider
  synthesizer → synthesis/rag strength preferred

CONSTRAINTS:
- ONLY use providers in the snapshot with daily_remaining > 0
- model string must be from that provider's "models" dict in snapshot
- Include analyst_1 only if analyst_count >= 2, analyst_2 if >= 3, etc.

Reply with ONLY valid JSON, no markdown, no text outside the JSON object:
{{
  "profile": "<simple_factual|current_factual|research|deep_research>",
  "scrapers": ["<names>"],
  "analyst_count": <1-4>,
  "roles": {{
    "triage": {{"provider": "<name>", "model": "<model>"}},
    "analyst_0": {{"provider": "<name>", "model": "<model>"}},
    "synthesizer": {{"provider": "<name>", "model": "<model>"}}
  }},
  "reasoning": "<one sentence>"
}}"""

    def _parse_plan(self, raw: str, snapshot: dict) -> dict:
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    return json.loads(fixed)
                except Exception:
                    pass

        logger.warning("Could not parse orchestrator JSON — using fallback")
        return self._fallback_plan(snapshot)

    def _validate_and_fix_plan(self, plan: dict, snapshot: dict) -> dict:
        available = list(snapshot.keys())
        if not available:
            return self._fallback_plan()

        plan.setdefault("profile", "research")
        plan.setdefault("scrapers", ["hackernews"])
        plan.setdefault("analyst_count", 1)
        plan.setdefault("roles", {})
        plan.setdefault("reasoning", "")

        roles = plan["roles"]

        role_needs = {
            "triage":      ["speed", "general"],
            "analyst_0":   ["reasoning", "analysis", "general"],
            "analyst_1":   ["reasoning", "analysis", "general"],
            "analyst_2":   ["analysis", "general"],
            "analyst_3":   ["analysis", "general"],
            "synthesizer": ["synthesis", "rag", "general"],
        }

        for role_name, needs in role_needs.items():
            if role_name not in roles:
                continue
            role = roles[role_name]
            provider = role.get("provider", "")

            if provider not in snapshot or snapshot[provider].get("daily_remaining", 0) == 0:
                replacement = self._pick_by_strength(snapshot, needs)
                if replacement:
                    provider = replacement
                    role["provider"] = provider
                else:
                    del roles[role_name]
                    continue

            provider_models = list(snapshot.get(provider, {}).get("models", {}).values())
            current_model = role.get("model", "")
            if current_model not in provider_models and provider_models:
                models_dict = snapshot[provider]["models"]
                role["model"] = models_dict.get("default") or provider_models[0]

        self._ensure_role(roles, "triage",      ["speed"],             snapshot, available)
        self._ensure_role(roles, "analyst_0",   ["reasoning", "analysis"], snapshot, available)
        self._ensure_role(roles, "synthesizer", ["synthesis", "rag"],  snapshot, available)

        for i in range(plan["analyst_count"], 4):
            roles.pop(f"analyst_{i}", None)

        return plan

    def _ensure_role(self, roles, role_name, needs, snapshot, available):
        if role_name in roles:
            return
        provider = self._pick_by_strength(snapshot, needs) or available[0]
        roles[role_name] = {
            "provider": provider,
            "model": self._default_model(snapshot, provider),
        }

    def _pick_by_strength(self, snapshot: dict, strengths: list) -> Optional[str]:
        best, best_remaining = None, -1
        for provider, info in snapshot.items():
            if info.get("daily_remaining", 0) <= 0:
                continue
            if any(s in info.get("strengths", []) for s in strengths):
                if info["daily_remaining"] > best_remaining:
                    best = provider
                    best_remaining = info["daily_remaining"]
        return best

    def _default_model(self, snapshot: dict, provider: str) -> str:
        models = snapshot.get(provider, {}).get("models", {})
        return models.get("default") or (list(models.values())[0] if models else "")

    def _fallback_plan(self, snapshot: Optional[dict] = None) -> dict:
        """
        Build a valid runnable plan entirely without an LLM call.
        Used when Gemini is rate-limited or unavailable.
        """
        if not snapshot:
            snapshot = self.pool.get_capabilities_snapshot()

        providers = list(snapshot.keys())
        if not providers:
            return {
                "profile": "research",
                "scrapers": ["hackernews"],
                "analyst_count": 1,
                "roles": {},
                "reasoning": "Fallback: no providers available",
            }

        fast   = self._pick_by_strength(snapshot, ["speed"]) or providers[0]
        reason = self._pick_by_strength(snapshot, ["reasoning", "analysis"]) or providers[0]
        synth  = self._pick_by_strength(snapshot, ["synthesis", "rag"]) or providers[-1]

        return {
            "profile": "research",
            "scrapers": ["hackernews"],
            "analyst_count": 1,
            "roles": {
                "triage": {
                    "provider": fast,
                    "model": self._default_model(snapshot, fast),
                },
                "analyst_0": {
                    "provider": reason,
                    "model": self._default_model(snapshot, reason),
                },
                "synthesizer": {
                    "provider": synth,
                    "model": self._default_model(snapshot, synth),
                },
            },
            "reasoning": "Fallback plan — Gemini unavailable, using best available providers.",
        }
