"""
Unified LLM Client Dispatcher & Test Prober
────────────────────────────────────────────
Executes LLM API requests across Gemini, Cohere, Groq, Cerebras, SambaNova,
OpenRouter, GitHub Models, Cloudflare, Hugging Face, and Ollama.
Includes key testing, latency measurement, and automated error categorization.
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any, Tuple
from google import genai
from google.genai import errors as genai_errors
from openai import AsyncOpenAI
import cohere

from core.gateway.models import (
    KeyTestResult, PROVIDER_SPECS, ProviderSpec
)

logger = logging.getLogger(__name__)


class UnifiedLLMClient:
    """Unified client capable of routing to any free-tier LLM provider."""

    @staticmethod
    async def test_key(
        provider: str,
        key_value: str,
        model: Optional[str] = None
    ) -> KeyTestResult:
        """
        Probe an API key with a minimal prompt to verify correctness and measure latency.
        """
        p_name = provider.lower().strip()
        spec = PROVIDER_SPECS.get(p_name)
        if not spec:
            return KeyTestResult(
                provider=p_name,
                model=model or "unknown",
                success=False,
                latency_ms=0.0,
                message=f"Unsupported provider: {p_name}"
            )

        target_model = model or spec.default_model
        t0 = time.time()

        try:
            prompt = "Respond with strictly the word: OK"
            reply = await UnifiedLLMClient.call_raw(
                provider=p_name,
                key_value=key_value,
                model=target_model,
                prompt=prompt,
                max_tokens=20,
                temperature=0.0
            )
            latency = (time.time() - t0) * 1000

            if reply and len(reply.strip()) > 0:
                return KeyTestResult(
                    provider=p_name,
                    model=target_model,
                    success=True,
                    latency_ms=round(latency, 2),
                    message=f"Success! Model responded: '{reply.strip()[:30]}'",
                )
            else:
                return KeyTestResult(
                    provider=p_name,
                    model=target_model,
                    success=False,
                    latency_ms=round(latency, 2),
                    message="Model returned empty response."
                )

        except Exception as e:
            latency = (time.time() - t0) * 1000
            err_msg = str(e)
            return KeyTestResult(
                provider=p_name,
                model=target_model,
                success=False,
                latency_ms=round(latency, 2),
                message=f"Authentication or model error: {err_msg[:200]}"
            )

    @staticmethod
    async def call_raw(
        provider: str,
        key_value: str,
        model: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.3
    ) -> str:
        """Directly call provider SDK without key vault tracking."""
        p_name = provider.lower().strip()

        if p_name == "gemini":
            client = genai.Client(api_key=key_value)
            try:
                resp = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt
                )
                return resp.text.strip() if resp and resp.text else ""
            finally:
                client.close()

        elif p_name == "cohere":
            co = cohere.AsyncClientV2(api_key=key_value)
            resp = await co.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            if resp.message and resp.message.content:
                return resp.message.content[0].text.strip()
            return ""

        else:
            # OpenAI-compatible: groq, cerebras, sambanova, openrouter, github, cloudflare, huggingface, ollama
            spec = PROVIDER_SPECS.get(p_name)
            base_url = spec.base_url if spec else "https://api.groq.com/openai/v1"
            
            client = AsyncOpenAI(
                api_key=key_value or "ollama",
                base_url=base_url
            )
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if resp.choices and len(resp.choices) > 0:
                return resp.choices[0].message.content or ""
            return ""
