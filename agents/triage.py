"""
Triage Agent
────────────
Scores each scraped chunk for relevance to the query (0–10).
Uses a fast, cheap model (high daily limits) since it calls once per chunk.
Chunks below the threshold are dropped before analysis.
"""

import logging
from agents.base_agent import BaseAgent
from core.key_pool import KeyPool

logger = logging.getLogger(__name__)


class TriageAgent(BaseAgent):

    def __init__(self, pool: KeyPool, provider: str, model: str):
        super().__init__("triage", pool, provider=provider, model=model)

    async def score_chunks(
        self,
        query: str,
        chunks: list[dict],
        threshold: float,
        query_id: str = "",
    ) -> list[dict]:
        """
        Score all chunks and return only those above threshold.
        Individual scoring failures are non-fatal — chunk gets score 5.0.
        """
        scored = []
        for chunk in chunks:
            score = await self._score_one(query, chunk, query_id)
            chunk["relevance_score"] = score
            if score >= threshold:
                scored.append(chunk)

        logger.info(f"[triage] kept {len(scored)}/{len(chunks)} chunks (threshold={threshold})")
        return scored

    async def _score_one(self, query: str, chunk: dict, query_id: str) -> float:
        content_preview = chunk.get("content", "")[:600]
        prompt = (
            f"You are a research librarian deciding whether a source is worth "
            f"an expert's time.\n\n"
            f"RESEARCH QUERY: {query}\n\n"
            f"SOURCE CONTENT:\n{content_preview}\n\n"
            f"Score this source's relevance and usefulness to the query:\n"
            f"10 = directly answers the query with specific, verifiable information\n"
            f"7-9 = highly relevant, contains useful specific details\n"
            f"4-6 = tangentially related or too general\n"
            f"1-3 = barely related\n"
            f"0 = completely irrelevant or spam\n\n"
            f"Reply with ONLY a single integer 0-10. Nothing else."
        )
        raw = await self.call(prompt, query_id=query_id, estimated_tokens=200)
        return self.parse_float(raw, default=5.0)
