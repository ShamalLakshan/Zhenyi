"""
Base Agent
──────────
All LLM agents inherit from this. Handles:
- Provider-specific API calls (Gemini, Cohere, OpenAI-compatible)
- Retry with exponential backoff
- Key pool integration
- JSON parsing with cleanup
- State store logging
- Never raises — returns empty string on failure

To support a new provider: add a branch in _call_provider().
"""

import asyncio
import json
import logging
import time
from typing import Optional

from google import genai
from google.genai import errors

from core.key_pool import KeyPool, KeyState
from core import state_store

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
def get_log_context():
    from core.pipeline import get_current_log_context
    return get_current_log_context()


class BaseAgent:
    """
    Base class for all LLM agents.

    Usage (direct):
        agent = BaseAgent("my_role", pool, provider="groq", model="llama-3.1-8b-instant")
        result = await agent.call("your prompt")

    Usage (subclass):
        class TriageAgent(BaseAgent):
            async def score(self, query, chunk):
                return await self.call(f"score this: {chunk}")
    """

    def __init__(
        self,
        agent_id: str,
        pool: KeyPool,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.pool = pool
        self.provider = provider or "groq"
        self.model = model or "llama-3.1-8b-instant"

    async def call(
        self,
        prompt: str,
        query_id: str = "",
        max_retries: int = 2,
        estimated_tokens: int = 500,
    ) -> str:
        """
        Call the LLM. Retries up to max_retries times with different keys.
        On rate limit (429) or quota error, immediately tries next available fallback key.
        Returns empty string on total failure — never raises.
        Logs full request/response payloads to debug context if available.
        """
        last_error = ""
        log_ctx = get_log_context()
        tried_keys = set()  # Track which keys we've already tried
        
        for attempt in range(max_retries + 1):
            # Pick key: prefer ready, otherwise try fallback with most quota
            key = self.pool.pick(self.provider)
            
            if key is None:
                # No ready keys — try fallback keys we haven't used yet
                fallback_keys = self.pool.get_fallback_keys(self.provider)
                available_fallbacks = [k for k in fallback_keys if k.env_var not in tried_keys]
                
                if available_fallbacks:
                    key = available_fallbacks[0]
                    logger.info(f"[{self.agent_id}] Switching to fallback key {key.env_var} "
                               f"({key.daily_remaining} quota remaining)")
                else:
                    # All keys exhausted or tried
                    fallback = self.pool.pick_or_wait(self.provider)
                    if fallback is None:
                        logger.warning(f"[{self.agent_id}] No keys configured for {self.provider}")
                        return ""
                    wait_time = max(0.0, fallback.cooldown_until - time.time())
                    if wait_time > 0 and wait_time < 70:
                        logger.info(f"[{self.agent_id}] Waiting {wait_time:.0f}s for key cooldown")
                        await asyncio.sleep(wait_time + 1)
                    key = self.pool.pick(self.provider)
                    if key is None:
                        return ""
            
            tried_keys.add(key.env_var)
            t0 = time.time()
            
            try:
                # Log request (if logging context available, non-blocking)
                request_dict = {
                    "model": self.model,
                    "provider": self.provider,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.3,
                }
                
                if log_ctx and query_id:
                    try:
                        await log_ctx.log_api_request(
                            self.agent_id, self.provider, self.model, attempt,
                            request_dict, estimated_tokens=estimated_tokens
                        )
                    except Exception as e:
                        logger.debug(f"[{self.agent_id}] Log request error (non-fatal): {e}")
                
                result = await self._call_provider(key, prompt)
                latency = (time.time() - t0) * 1000
                key.record_usage(estimated_tokens)

                # Log response (if logging context available, non-blocking)
                if log_ctx and query_id:
                    try:
                        await log_ctx.log_api_response(
                            self.agent_id, self.provider, self.model, attempt,
                            response_dict={"content": result[:500]},
                            response_code=200, latency_ms=latency,
                            actual_tokens_out=len(result.split()) * 1.3  # Rough estimate
                        )
                    except Exception as e:
                        logger.debug(f"[{self.agent_id}] Log response error (non-fatal): {e}")

                if query_id:
                    await state_store.log_agent_output(
                        query_id, self.agent_id, self.provider,
                        self.model, latency,
                        {"preview": result[:300], "attempt": attempt, "key": key.env_var}
                    )
                return result

            except Exception as e:
                last_error = str(e)
                latency = (time.time() - t0) * 1000
                error_lower = last_error.lower()
                
                # Classify error type
                is_rate_limit = "429" in error_lower
                is_quota = any(x in error_lower for x in ["quota", "exceeded", "out of quota"])
                is_recoverable = is_rate_limit or is_quota
                
                key.record_error(is_rate_limit=is_rate_limit, is_quota=is_quota)
                
                logger.warning(
                    f"[{self.agent_id}] attempt {attempt+1}/{max_retries+1} "
                    f"failed ({self.provider}, {key.env_var}): {last_error[:120]}"
                )
                
                # Log error response (if logging context available, non-blocking)
                if log_ctx and query_id:
                    try:
                        await log_ctx.log_api_response(
                            self.agent_id, self.provider, self.model, attempt,
                            response_code=500, latency_ms=latency,
                            error_message=last_error[:500]
                        )
                    except Exception as e:
                        logger.debug(f"[{self.agent_id}] Log error response failed (non-fatal): {e}")
                
                # If rate limit or quota, try fallback key immediately (don't wait)
                if is_recoverable and attempt < max_retries:
                    fallback_keys = self.pool.get_fallback_keys(self.provider)
                    available_fallbacks = [k for k in fallback_keys if k.env_var not in tried_keys]
                    if available_fallbacks:
                        logger.info(f"[{self.agent_id}] Rate limit/quota on {key.env_var}, "
                                   f"trying fallback immediately")
                        continue  # Try next iteration with fallback key
                
                # For non-recoverable errors or if no more fallbacks, back off
                if attempt < max_retries:
                    wait_seconds = 2 ** attempt
                    logger.debug(f"[{self.agent_id}] Backing off for {wait_seconds}s before retry")
                    await asyncio.sleep(wait_seconds)

        logger.error(f"[{self.agent_id}] All {max_retries+1} attempts failed. Last: {last_error[:200]}")
        return ""

    async def _call_provider(self, key: KeyState, prompt: str) -> str:
        """
        Routes to the correct provider SDK.
        All providers normalised to: send prompt → return string.
        """
        if self.provider == "gemini":
            return await self._call_gemini(key.value, prompt)
        elif self.provider == "cohere":
            return await self._call_cohere(key.value, prompt)
        else:
            # OpenAI-compatible: groq, openrouter, cerebras, github
            return await self._call_openai_compatible(key.value, prompt)

    async def _call_gemini(self, api_key: str, prompt: str) -> str:
        client = genai.Client(api_key=api_key)
        try:
            resp = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt
            )
            return resp.text.strip()
        finally:
            client.close()

    async def _call_cohere(self, api_key: str, prompt: str) -> str:
        import cohere
        co = cohere.AsyncClientV2(api_key=api_key)
        resp = await co.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.message.content[0].text.strip()

    async def _call_openai_compatible(self, api_key: str, prompt: str) -> str:
        from openai import AsyncOpenAI
        base_url = self.pool.get_base_url(self.provider)
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        resp = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    # ─── Utilities ────────────────────────────────────────────────────────────

    def parse_json(self, raw: str) -> dict:
        """
        Robustly parse JSON from LLM output.
        Handles markdown fences, leading text, trailing text.
        Returns {} on failure — never raises.
        """
        if not raw:
            return {}

        # Strip markdown code fences
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:]
                part = part.strip()
                if part.startswith("{"):
                    text = part
                    break

        # Find the first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}

        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Try to fix common issues: trailing commas
            import re
            fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                return json.loads(fixed)
            except Exception:
                return {}

    def parse_float(self, raw: str, default: float = 5.0) -> float:
        """Extract first float from a string."""
        if not raw:
            return default
        import re
        matches = re.findall(r"\d+\.?\d*", raw.strip())
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                pass
        return default
