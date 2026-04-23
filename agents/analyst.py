"""
Analyst Agent
─────────────
Receives a slice of filtered chunks and analyses them for the query.
Returns structured JSON: findings, contradictions, confidence, gaps.
On parse failure, wraps the raw text in a minimal valid result rather than failing.
"""

import logging
from agents.base_agent import BaseAgent
from core.key_pool import KeyPool

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):

    def __init__(self, agent_id: str, pool: KeyPool, provider: str, model: str):
        super().__init__(agent_id, pool, provider=provider, model=model)

    async def analyse(
        self,
        query: str,
        chunks: list[dict],
        query_id: str = "",
        log_ctx=None,
    ) -> dict:
        """
        Analyse a set of chunks for the query.
        Returns a structured dict regardless of LLM output quality.
        log_ctx: optional logging context for debug logging
        """
        if not chunks:
            return self._empty_result("no chunks assigned")

        context = self._build_context(chunks)
        prompt = (
            f"You are a specialist research analyst with deep domain expertise. "
            f"Your job is to extract maximum useful information from these sources.\n\n"
            f"RESEARCH QUERY: {query}\n\n"
            f"SOURCES:\n{context}\n\n"
            f"Instructions:\n"
            f"- Extract SPECIFIC facts: names, numbers, versions, dates, part numbers, "
            f"specifications, prices, authors, institutions — not generalities\n"
            f"- Note direct quotes or data points from sources where relevant\n"
            f"- Identify what sources AGREE on and what they CONTRADICT\n"
            f"- Flag any claims that lack a source or seem uncertain\n"
            f"- Do NOT pad with filler. Every finding must be a concrete, specific claim.\n\n"
            f"Respond ONLY with valid JSON, no markdown, no preamble:\n"
            f'{{\n'
            f'  "confidence": <float 0.0-1.0 based on source quality and agreement>,\n'
            f'  "key_findings": [\n'
            f'    "Specific finding with concrete detail — not a vague summary",\n'
            f'    "Another specific finding"\n'
            f'  ],\n'
            f'  "contradictions": ["Source A says X but Source B says Y — be explicit"],\n'
            f'  "needs_more_info": ["Specific gap that would improve the answer"]\n'
            f'}}'
        )

        raw = await self.call(prompt, query_id=query_id, estimated_tokens=800)

        # Log reasoning step (non-blocking)
        if log_ctx and query_id:
            try:
                await log_ctx.log_agent_reasoning(
                    self.agent_id, "analyst", 1,
                    f"Analyzing {len(chunks)} chunks",
                    f"Generated analysis response",
                    len(chunks)
                )
            except Exception as e:
                logger.debug(f"[{self.agent_id}] Log reasoning error (non-fatal): {e}")

        if not raw:
            return self._empty_result("empty response from provider")

        parsed = self.parse_json(raw)
        if parsed and "key_findings" in parsed:
            # Normalise fields
            result = {
                "confidence": float(parsed.get("confidence", 0.5)),
                "key_findings": [str(f) for f in parsed.get("key_findings", [])],
                "contradictions": [str(c) for c in parsed.get("contradictions", [])],
                "needs_more_info": [str(g) for g in parsed.get("needs_more_info", [])],
                "agent_id": self.agent_id,
                "provider": self.provider,
            }
            
            # Log successful parsing (non-blocking)
            if log_ctx and query_id:
                try:
                    await log_ctx.log_agent_reasoning(
                        self.agent_id, "analyst", 2,
                        f"Successfully parsed {len(result.get('key_findings', []))} findings",
                        "Analysis complete",
                        0,
                        result.get("confidence", 0.5)
                    )
                except Exception as e:
                    logger.debug(f"[{self.agent_id}] Log parsing error (non-fatal): {e}")
            
            return result

        # Parse failed — wrap raw text as a finding rather than losing it
        logger.warning(f"[{self.agent_id}] JSON parse failed, wrapping raw text")
        return {
            "confidence": 0.3,
            "key_findings": [raw[:600]] if raw else [],
            "contradictions": [],
            "needs_more_info": ["structured parse failed"],
            "agent_id": self.agent_id,
            "provider": self.provider,
        }

    def _build_context(self, chunks: list[dict]) -> str:
        parts = []
        for i, c in enumerate(chunks):
            url = c.get("url", "unknown")
            source = c.get("source", "unknown")
            content = c.get("content", "")[:1000]
            parts.append(f"[Source {i+1}] ({source}) {url}\n{content}")
        return "\n\n---\n\n".join(parts)

    def _empty_result(self, reason: str) -> dict:
        return {
            "confidence": 0.0,
            "key_findings": [],
            "contradictions": [],
            "needs_more_info": [reason],
            "agent_id": self.agent_id,
            "provider": self.provider,
        }
