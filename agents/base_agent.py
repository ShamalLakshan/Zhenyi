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

from core.key_pool import KeyPool, KeyState
from core import state_store

logger = logging.getLogger(__name__)


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
        Returns empty string on total failure — never raises.
        """
        last_error = ""
        for attempt in range(max_retries + 1):
            key = self.pool.pick(self.provider)

            if key is None:
                # All keys exhausted — wait for the shortest cooldown
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

            t0 = time.time()
            try:
                result = await self._call_provider(key, prompt)
                latency = (time.time() - t0) * 1000
                key.record_usage(estimated_tokens)

                if query_id:
                    await state_store.log_agent_output(
                        query_id, self.agent_id, self.provider,
                        self.model, latency,
                        {"preview": result[:300], "attempt": attempt}
                    )
                return result

            except Exception as e:
                last_error = str(e)
                latency = (time.time() - t0) * 1000
                is_rate_limit = any(
                    x in last_error.lower()
                    for x in ["429", "rate limit", "quota", "too many requests"]
                )
                key.record_error(is_rate_limit=is_rate_limit)
                logger.warning(
                    f"[{self.agent_id}] attempt {attempt+1}/{max_retries+1} "
                    f"failed ({self.provider}): {last_error[:120]}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

        logger.error(f"[{self.agent_id}] All attempts failed. Last: {last_error[:200]}")
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
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self.model)
        # Gemini SDK is synchronous — run in thread pool to avoid blocking event loop
        resp = await asyncio.to_thread(model.generate_content, prompt)
        return resp.text.strip()

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
