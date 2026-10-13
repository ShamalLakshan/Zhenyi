"""
Unified LLM Gateway Orchestrator
─────────────────────────────────
Centrally routes LLM calls across all configured free-tier API keys.
Enforces sliding window rate limits, performs automated failover,
and records token metrics and latency.
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple

from core.gateway.models import (
    KeyModel, KeyStatus, ProviderTier, ResearchMode, PROVIDER_SPECS
)
from core.gateway.key_vault import KeyVault
from core.gateway.rate_limiter import SlidingWindowRateLimiter
from core.gateway.llm_client import UnifiedLLMClient

logger = logging.getLogger(__name__)


class LLMGateway:
    """Singleton Gateway managing all LLM invocations across keys and tiers."""

    _instance: Optional["LLMGateway"] = None
    _lock = asyncio.Lock()

    def __init__(self, db_path: str = "zhenyi.db"):
        self.vault = KeyVault(db_path=db_path)
        self.rate_limiter = SlidingWindowRateLimiter()
        self.research_mode = ResearchMode.DEEP_RESEARCH

    @classmethod
    async def get_instance(cls, db_path: str = "zhenyi.db") -> "LLMGateway":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    gw = cls(db_path=db_path)
                    await gw.vault.init_vault()
                    cls._instance = gw
        return cls._instance

    def set_research_mode(self, mode: ResearchMode):
        self.research_mode = mode
        logger.info(f"Gateway research mode set to: {mode.value}")

    async def call_provider(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        estimated_tokens: int = 500,
        session_id: Optional[str] = None,
        message_id: Optional[str] = None,
        max_retries: int = 2
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Execute prompt against a specific provider with automatic key failover.
        Returns: (response_text, telemetry_dict)
        """
        p_name = provider.lower().strip()
        spec = PROVIDER_SPECS.get(p_name)
        target_model = model or (spec.default_model if spec else "llama-3.1-8b-instant")
        
        last_error = ""
        tried_key_ids = set()

        for attempt in range(max_retries + 1):
            key_info = await self.vault.pick_best_key(p_name)
            if not key_info:
                # No ready keys for this provider
                logger.warning(f"No available ready keys for provider '{p_name}'")
                break

            key_model, raw_key = key_info
            if key_model.id in tried_key_ids:
                # All active keys already attempted
                break
            tried_key_ids.add(key_model.id)

            # Check rate limiter
            allowed, wait_sec = self.rate_limiter.can_consume(
                key_model.id, key_model.rpm_limit, estimated_tokens=estimated_tokens
            )
            if not allowed:
                if wait_sec > 0 and wait_sec <= 2.0:
                    await asyncio.sleep(wait_sec)
                else:
                    # Put in quick cooldown and try another key
                    await self.vault.record_error(key_model.id, is_rate_limit=True, cooldown_seconds=wait_sec)
                    continue

            t0 = time.time()
            try:
                reply = await UnifiedLLMClient.call_raw(
                    provider=p_name,
                    key_value=raw_key,
                    model=target_model,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                latency = (time.time() - t0) * 1000

                # Approximate tokens
                tokens_in = max(1, len(prompt.split()) * 4 // 3)
                tokens_out = max(1, len(reply.split()) * 4 // 3)

                # Record consumption in limiter & persistent vault
                self.rate_limiter.record_consumption(key_model.id, tokens=tokens_in + tokens_out)
                await self.vault.record_usage(key_model.id, tokens_in, tokens_out, latency)

                telemetry = {
                    "provider": p_name,
                    "model": target_model,
                    "key_id": key_model.id,
                    "key_label": key_model.label,
                    "latency_ms": round(latency, 2),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "attempt": attempt,
                }
                return reply, telemetry

            except Exception as e:
                latency = (time.time() - t0) * 1000
                last_error = str(e)
                err_lower = last_error.lower()
                is_rate_limit = "429" in err_lower or "rate limit" in err_lower
                is_quota = "quota" in err_lower or "exceeded" in err_lower

                logger.warning(
                    f"Call failed on {p_name} ({key_model.label}) attempt {attempt+1}: {last_error[:120]}"
                )

                cooldown = 65.0 if is_rate_limit else (300.0 if is_quota else 30.0)
                await self.vault.record_error(
                    key_model.id, is_rate_limit=is_rate_limit, is_quota=is_quota, cooldown_seconds=cooldown
                )

                if attempt < max_retries and not (is_rate_limit or is_quota):
                    await asyncio.sleep(2 ** attempt)

        # Provider failed across attempts
        return "", {
            "provider": p_name,
            "model": target_model,
            "error": last_error,
            "success": False
        }

    async def call_tiered_role(
        self,
        role: str,
        prompt: str,
        preferred_provider: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Select the best provider according to role and current research mode.
        Role mappings:
          - 'triage': Tier 0 (Groq, Cerebras)
          - 'analyst': Tier 1 (SambaNova, OpenRouter, GitHub)
          - 'synthesizer': Tier 3 (Cohere) or Tier 2 (Gemini)
          - 'planner': Tier 2 (Gemini) or Tier 1 (SambaNova, Groq)
        """
        tier_map = {
            "triage": ["groq", "cerebras", "cloudflare", "github"],
            "analyst": ["sambanova", "openrouter", "github", "groq", "gemini"],
            "synthesizer": ["cohere", "gemini", "sambanova", "openrouter"],
            "planner": ["gemini", "sambanova", "groq", "openrouter"],
        }

        # If in economy mode, prefer Tier 0 providers
        if self.research_mode == ResearchMode.ECONOMY:
            candidate_providers = ["groq", "cerebras", "cloudflare", "github", "gemini"]
        else:
            candidate_providers = tier_map.get(role, ["groq", "gemini", "sambanova", "openrouter"])

        if preferred_provider and preferred_provider in candidate_providers:
            candidate_providers.remove(preferred_provider)
            candidate_providers.insert(0, preferred_provider)

        # Try candidates in order
        for prov in candidate_providers:
            reply, telemetry = await self.call_provider(
                provider=prov,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            if reply:
                telemetry["role"] = role
                return reply, telemetry

        # Fallback to local Ollama if available
        reply, telemetry = await self.call_provider("ollama", prompt, max_tokens=max_tokens)
        telemetry["role"] = role
        return reply, telemetry
