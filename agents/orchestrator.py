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
import warnings
from typing import Optional

# Suppress deprecation warning for google.generativeai (using stable version despite deprecation)
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

import google.generativeai as genai

from core.key_pool import KeyPool
from core import state_store
from core.exceptions import NoAvailableKeysError

logger = logging.getLogger(__name__)

AVAILABLE_SCRAPERS = ["hackernews", "web", "arxiv", "wikipedia", "ddgs", "openalex", "open_meteo", "sec_edgar", "youtube"]

# Query intent detection keywords for smart scraper selection
QUERY_INTENT_KEYWORDS = {
    "academic": {
        "keywords": ["paper", "research", "study", "journal", "arxiv", "doi", "citation", "peer review", "methodology"],
        "scrapers": ["arxiv", "openalex", "web"],
    },
    "current_events": {
        "keywords": ["latest", "recent", "news", "today", "breaking", "update", "2024", "2025", "2026", "announce", "release"],
        "scrapers": ["hackernews", "web", "ddgs"],
    },
    "knowledge_base": {
        "keywords": ["what is", "definition", "explain", "how does", "background", "history", "overview", "introduction"],
        "scrapers": ["wikipedia", "web"],
    },
    "weather_climate": {
        "keywords": ["weather", "temperature", "forecast", "climate", "wind", "rain", "celsius", "fahrenheit"],
        "scrapers": ["open_meteo", "web"],
    },
    "finance_sec": {
        "keywords": ["sec filing", "10-k", "10-q", "stock", "earnings", "financial", "sec.gov", "cik", "ticker"],
        "scrapers": ["sec_edgar", "web"],
    },
    "video_multimedia": {
        "keywords": ["video", "youtube", "tutorial", "demo", "stream", "channel", "playlist", "watch"],
        "scrapers": ["youtube", "web"],
    },
    "tech_trends": {
        "keywords": ["algorithm", "github", "code", "library", "framework", "open source", "repository", "commit"],
        "scrapers": ["hackernews", "web", "ddgs"],
    },
    "community_opinion": {
        "keywords": ["forum", "community", "people", "opinion", "experience", "recommend", "review", "discussion"],
        "scrapers": ["hackernews", "web"],
    },
    "specification_technical": {
        "keywords": ["spec", "datasheet", "part", "model", "schematic", "component", "manual", "guide", "documentation", "tutorial"],
        "scrapers": ["web", "arxiv"],
    },
}


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

    async def plan(self, query: str, query_id: str, log_ctx=None) -> dict:
        """
        Produce a full execution plan for this query.
        Returns a dict with: profile, scrapers, analyst_count, roles, reasoning.
        Never raises — falls back to a safe plan on any error.
        log_ctx: optional logging context for debug logging
        """
        try:
            api_key, model, key_state = self.pool.get_orchestrator_key()
        except NoAvailableKeysError:
            logger.error("No orchestrator keys available — using fallback plan")
            plan = self._fallback_plan(snapshot=None, query=query)
            await state_store.log_thought(query_id, "orchestrator", "fallback: no keys")
            
            # Log plan to debug context (non-blocking)
            if log_ctx and query_id:
                try:
                    await log_ctx.log_orchestrator_plan(
                        "No orchestrator keys available",
                        plan.get("profile", "research"),
                        plan.get("scrapers", []),
                        plan.get("roles", {}),
                        fallback_used=True
                    )
                except Exception as e:
                    logger.debug(f"Log orchestrator plan error (non-fatal): {e}")
            
            return plan

        snapshot = self.pool.get_capabilities_snapshot()
        if not snapshot:
            logger.error("No providers available in snapshot — using fallback plan")
            plan = self._fallback_plan(snapshot=None, query=query)
            await state_store.log_thought(query_id, "orchestrator", "fallback: empty snapshot")
            
            # Log plan to debug context (non-blocking)
            if log_ctx and query_id:
                try:
                    await log_ctx.log_orchestrator_plan(
                        "No providers available in snapshot",
                        plan.get("profile", "research"),
                        plan.get("scrapers", []),
                        plan.get("roles", {}),
                        fallback_used=True
                    )
                except Exception as e:
                    logger.debug(f"Log orchestrator plan error (non-fatal): {e}")
            
            return plan

        prompt = self._build_prompt(query, snapshot)

        # Try primary key first, then fallback keys on rate limit
        tried_keys = [key_state]
        
        while tried_keys:
            current_key_state = tried_keys.pop(0)
            
            try:
                genai.configure(api_key=current_key_state.value)
                gmodel = genai.GenerativeModel(model)
                resp = await asyncio.to_thread(gmodel.generate_content, prompt)
                raw = resp.text.strip()
                current_key_state.record_usage(estimated_tokens=800)
                logger.info(f"Orchestrator succeeded with {current_key_state.env_var}")
                break

            except Exception as e:
                error_str = str(e)
                is_rate_limit = any(
                    x in error_str.lower()
                    for x in ["429", "quota", "rate limit", "too many requests", "exceeded"]
                )
                
                if is_rate_limit:
                    current_key_state.record_error(is_rate_limit=True, is_quota=True)
                    delay = _extract_retry_delay(error_str)
                    current_key_state.set_cooldown(delay)
                    
                    logger.warning(
                        f"Orchestrator 429 on {current_key_state.env_var} — "
                        f"cooling for {delay:.0f}s. Trying fallback keys..."
                    )
                    
                    # Try next fallback key
                    fallback_keys = self.pool.get_fallback_keys("gemini")
                    for fk in fallback_keys:
                        if fk.env_var not in [k.env_var for k in [current_key_state] + tried_keys]:
                            tried_keys.insert(0, fk)
                            logger.info(f"Trying fallback key {fk.env_var}")
                    
                    if tried_keys:
                        continue  # Try next key
                    else:
                        logger.error("No fallback keys available for orchestrator")
                        raw = None  # Will fall back to non-LLM plan
                else:
                    current_key_state.record_error(is_rate_limit=False)
                    logger.error(f"Orchestrator API call failed: {e}")
                    raw = None  # Will fall back to non-LLM plan
        
        # Check if we got a successful response
        if not raw or raw == "None":
            plan = self._fallback_plan(snapshot, query=query)
            await state_store.log_thought(
                query_id, "orchestrator",
                f"fallback: rate_limit (tried all keys)"
            )
            
            # Log fallback plan to debug context (non-blocking)
            if log_ctx and query_id:
                try:
                    await log_ctx.log_orchestrator_plan(
                        f"Orchestrator rate limited on all keys, falling back",
                        plan.get("profile", "research"),
                        plan.get("scrapers", []),
                        plan.get("roles", {}),
                        fallback_used=True
                    )
                except Exception as log_e:
                    logger.debug(f"Log orchestrator plan error (non-fatal): {log_e}")
            
            return plan

        plan = self._parse_plan(raw, snapshot)
        plan = self._validate_and_fix_plan(plan, snapshot)

        await state_store.log_thought(
            query_id, "orchestrator_plan",
            f"profile={plan['profile']} scrapers={plan['scrapers']} "
            f"analysts={plan['analyst_count']} | {plan.get('reasoning', '')}"
        )
        
        # Log successful plan to debug context (non-blocking)
        if log_ctx and query_id:
            try:
                await log_ctx.log_orchestrator_plan(
                    plan.get("reasoning", "Plan generated successfully"),
                    plan.get("profile", "research"),
                    plan.get("scrapers", []),
                    plan.get("roles", {}),
                    fallback_used=False
                )
            except Exception as e:
                logger.debug(f"Log orchestrator plan error (non-fatal): {e}")
        
        return plan

    def _build_prompt(self, query: str, snapshot: dict) -> str:
        # Detect query intent for smart scraper suggestions
        intent = self._detect_query_intent(query)
        suggested_scrapers = QUERY_INTENT_KEYWORDS.get(intent, {}).get("scrapers", ["hackernews", "web"])
        
        return f"""You are the orchestrator of a research agent system.
Analyse the user query and produce a JSON execution plan.

USER QUERY:
{query}

AVAILABLE PROVIDERS (live state — only use providers listed here):
{json.dumps(snapshot, indent=2)}

AVAILABLE SCRAPERS: {AVAILABLE_SCRAPERS}

SUGGESTED SCRAPERS FOR THIS QUERY: {suggested_scrapers}

PLANNING RULES:
Profile selection and scraper requirements:
  simple_factual  → for definitional/factual queries. scrapers: [] (direct LLM analysis only)
  current_factual → for recent news/status. scrapers: MUST select 1-2 from suggested
  research        → for multi-source queries. scrapers: MUST select 2-3 from suggested
  deep_research   → for complex/philosophical/technical. scrapers: MUST select ALL suggested scrapers

CRITICAL: The scraper count MUST match the profile:
- If you choose "deep_research", you MUST include all suggested scrapers
- If you choose "research", you MUST include 2-3 suggested scrapers
- If you choose "current_factual", you MUST include 1-2 suggested scrapers
- Only choose "simple_factual" if the query is asking for pure definitions/facts with NO external research needed

For philosophical/ethical/hypothetical queries → use "deep_research" with suggested scrapers (for context/precedent research)
For current events/news → use "current_factual" with news scrapers
For general research → use "research" with multiple sources

Role assignment:
  triage      → fastest provider (high daily_remaining + speed strength)
  analyst     → best reasoning provider
  synthesizer → synthesis/rag strength preferred

Triage mode (choose based on query complexity):
  scraper_only  → simple queries: fast heuristic scoring only
  llm_only      → complex/nuanced queries: LLM scoring for all chunks
  hybrid        → balanced: heuristic + LLM for borderline chunks (RECOMMENDED)

CONSTRAINTS:
- ONLY use providers in the snapshot with daily_remaining > 0
- model string must be from that provider's "models" dict in snapshot
- Include analyst_1 only if analyst_count >= 2, analyst_2 if >= 3, etc.
- SCRAPER COUNT VALIDATION:
  * If profile=simple_factual: scrapers must be empty []
  * If profile=current_factual: scrapers must have 1-2 items from suggested list
  * If profile=research: scrapers must have 2-3 items from suggested list  
  * If profile=deep_research: scrapers must include ALL suggested scrapers
- DO NOT override profile requirements based on reasoning. Profile MUST determine scraper count.

Reply with ONLY valid JSON, no markdown, no text outside the JSON object:
{{
  "profile": "<simple_factual|current_factual|research|deep_research>",
  "scrapers": ["<names>"],
  "analyst_count": <1-4>,
  "triage_mode": "<scraper_only|llm_only|hybrid>",
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
        plan.setdefault("triage_mode", "hybrid")  # Default to hybrid mode
        plan.setdefault("roles", {})
        plan.setdefault("reasoning", "")

        # Validate triage_mode
        valid_modes = {"scraper_only", "llm_only", "hybrid"}
        if plan["triage_mode"] not in valid_modes:
            plan["triage_mode"] = "hybrid"
            logger.warning(f"Invalid triage_mode, defaulting to hybrid")

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

    def _detect_query_intent(self, query: str) -> str:
        """
        Analyze query to detect intent category.
        Returns the intent name or "general" as fallback.
        
        Match specificity: More specific intents checked first (weather, finance)
        before generic ones (knowledge_base).
        """
        q = query.lower()
        
        # Check specific intents first (avoid false matches with generic intents)
        for intent in ["weather_climate", "finance_sec", "video_multimedia", "academic"]:
            config = QUERY_INTENT_KEYWORDS.get(intent, {})
            keywords = config.get("keywords", [])
            if any(kw in q for kw in keywords):
                logger.debug(f"[orchestrator] Detected intent: {intent}")
                return intent
        
        # Then check generic intents
        for intent in ["current_events", "knowledge_base", "tech_trends", "community_opinion", "specification_technical"]:
            config = QUERY_INTENT_KEYWORDS.get(intent, {})
            keywords = config.get("keywords", [])
            if any(kw in q for kw in keywords):
                logger.debug(f"[orchestrator] Detected intent: {intent}")
                return intent
        
        return "general"

    def _select_scrapers(self, snapshot: Optional[dict] = None, query: str = "") -> list[str]:
        """
        Smart scraper selection based on query intent and availability.
        Returns a prioritized list of available scrapers.
        """
        intent = self._detect_query_intent(query)
        
        # Get priority scrapers for this intent
        priority_scrapers = QUERY_INTENT_KEYWORDS.get(intent, {}).get("scrapers", ["hackernews", "web"])
        
        # Build final list: prioritized scrapers that are available, then any other available
        selected = []
        for scraper in priority_scrapers:
            if scraper in AVAILABLE_SCRAPERS and scraper not in selected:
                selected.append(scraper)
        
        # Backfill with any remaining available scrapers from the actual registry
        # (we can't check registry here, so use hardcoded fallback)
        for scraper in AVAILABLE_SCRAPERS:
            if scraper not in selected and scraper in ["hackernews", "web"]:
                selected.append(scraper)
        
        # Ensure at least one scraper
        if not selected:
            selected = ["hackernews"]
        
        logger.debug(f"[orchestrator] Query intent='{intent}' → scrapers={selected}")
        return selected

    def _fallback_plan(self, snapshot: Optional[dict] = None, query: str = "") -> dict:
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
                "triage_mode": "scraper_only",  # Fast fallback
                "roles": {},
                "reasoning": "Fallback: no providers available",
            }

        fast   = self._pick_by_strength(snapshot, ["speed"]) or providers[0]
        reason = self._pick_by_strength(snapshot, ["reasoning", "analysis"]) or providers[0]
        synth  = self._pick_by_strength(snapshot, ["synthesis", "rag"]) or providers[-1]

        # Smart scraper selection based on query intent
        scrapers = self._select_scrapers(snapshot, query)

        return {
            "profile": "research",
            "scrapers": scrapers,
            "analyst_count": 1,
            "triage_mode": "hybrid",  # Balanced approach for fallback
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
