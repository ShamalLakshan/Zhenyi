"""
Triage Agent
────────────
Scores each scraped chunk for relevance to the query (0–10).
Supports three modes:
  1. scraper_only - fast heuristic-based scoring (keyword matching, source quality)
  2. llm_only - LLM-based scoring (slower, higher accuracy)
  3. hybrid - both scrapers (quick) + LLM (augmentation), merged with dedup

Uses a fast, cheap model (high daily limits) since it calls once per chunk.
Chunks below the threshold are dropped before analysis.
"""

import logging
import re
import asyncio
from dataclasses import dataclass
from typing import Literal
from agents.base_agent import BaseAgent
from core.key_pool import KeyPool

logger = logging.getLogger(__name__)


@dataclass
class TriageScore:
    """Score result with source metadata."""
    source_id: str
    content: str
    scraper_score: float = 0.0
    llm_score: float = 0.0
    final_score: float = 0.0
    scoring_method: str = "unknown"  # "scraper", "llm", "hybrid"


class TriageAgent(BaseAgent):

    def __init__(self, pool: KeyPool, provider: str, model: str):
        super().__init__("triage", pool, provider=provider, model=model)

    async def score_chunks(
        self,
        query: str,
        chunks: list[dict],
        threshold: float,
        query_id: str = "",
        mode: Literal["scraper_only", "llm_only", "hybrid"] = "hybrid",
    ) -> list[dict]:
        """
        Score all chunks and return only those above threshold.
        
        Args:
            query: User query for relevance context
            chunks: List of chunks with 'content', 'source', 'url' fields
            threshold: Minimum score to keep (0-10)
            query_id: For logging context
            mode: Scoring mode - scraper_only (fast), llm_only (accurate), hybrid (balanced)
        
        Returns: List of scored chunks above threshold
        """
        if not chunks:
            return []
        
        if mode == "scraper_only":
            scored = await self._score_chunks_scraper_only(query, chunks, query_id)
        elif mode == "llm_only":
            scored = await self._score_chunks_llm_only(query, chunks, query_id)
        else:  # hybrid
            scored = await self._score_chunks_hybrid(query, chunks, query_id)
        
        # Filter by threshold
        kept = [c for c in scored if c.get("relevance_score", 0) >= threshold]
        logger.info(
            f"[triage] mode={mode} kept {len(kept)}/{len(chunks)} chunks "
            f"(threshold={threshold})"
        )
        return kept

    async def _score_chunks_scraper_only(
        self,
        query: str,
        chunks: list[dict],
        query_id: str,
    ) -> list[dict]:
        """Fast heuristic-based scoring without LLM calls."""
        scored = []
        query_words = set(query.lower().split())
        
        for chunk in chunks:
            score = self._heuristic_score(query, chunk, query_words)
            chunk["relevance_score"] = score
            chunk["scoring_method"] = "scraper_heuristic"
            scored.append(chunk)
        
        return scored

    async def _score_chunks_llm_only(
        self,
        query: str,
        chunks: list[dict],
        query_id: str,
    ) -> list[dict]:
        """LLM-based scoring for all chunks."""
        scored = []
        for chunk in chunks:
            score = await self._score_one_llm(query, chunk, query_id)
            chunk["relevance_score"] = score
            chunk["scoring_method"] = "llm"
            scored.append(chunk)
        
        return scored

    async def _score_chunks_hybrid(
        self,
        query: str,
        chunks: list[dict],
        query_id: str,
    ) -> list[dict]:
        """
        Hybrid mode: Fast scraper scoring first, then LLM augmentation for borderline chunks.
        Chunks with high confidence from scraper (9-10 or 0-2) skip LLM.
        Medium confidence (3-8) get LLM augmentation for accuracy.
        """
        query_words = set(query.lower().split())
        
        # Step 1: Fast heuristic scoring for all chunks
        scored = []
        borderline = []  # Chunks that need LLM augmentation
        
        for chunk in chunks:
            scraper_score = self._heuristic_score(query, chunk, query_words)
            
            if scraper_score >= 9 or scraper_score <= 2:
                # High confidence from scraper — use as-is
                chunk["relevance_score"] = scraper_score
                chunk["scoring_method"] = "scraper_confident"
                scored.append(chunk)
            else:
                # Medium confidence — queue for LLM augmentation
                chunk["_scraper_score"] = scraper_score
                borderline.append(chunk)
        
        # Step 2: Parallel LLM scoring for borderline chunks (faster than sequential)
        if borderline:
            llm_tasks = [
                self._score_one_llm(query, chunk, query_id)
                for chunk in borderline
            ]
            llm_scores = await asyncio.gather(*llm_tasks, return_exceptions=True)
            
            for chunk, llm_result in zip(borderline, llm_scores):
                if isinstance(llm_result, Exception):
                    logger.warning(f"LLM score failed for chunk, using scraper: {llm_result}")
                    chunk["relevance_score"] = chunk["_scraper_score"]
                    chunk["scoring_method"] = "scraper_fallback"
                else:
                    # Average scraper and LLM scores for hybrid confidence
                    final_score = (chunk["_scraper_score"] + llm_result) / 2.0
                    chunk["relevance_score"] = final_score
                    chunk["scoring_method"] = "hybrid"
                
                chunk.pop("_scraper_score", None)
                scored.append(chunk)
        
        return scored

    def _heuristic_score(self, query: str, chunk: dict, query_words: set) -> float:
        """
        Fast heuristic scoring based on:
        - Keyword density (query words in content)
        - Source quality (domain reputation)
        - Content length (too short = low quality)
        - Specificity indicators (numbers, citations, etc.)
        """
        content = chunk.get("content", "").lower()
        source = chunk.get("source", "unknown").lower()
        url = chunk.get("url", "").lower()
        
        if not content or len(content) < 50:
            return 0.0  # Too short to be useful
        
        # Keyword matching (max 3 points)
        keyword_matches = sum(1 for word in query_words if word in content)
        keyword_score = min(3.0, keyword_matches * 0.5)
        
        # Source quality (max 3 points)
        high_quality_sources = {
            "arxiv", "scholar.google", "nature", "science", "ieee",
            "wikipedia", "github", "stackoverflow", "medium", "dev.to"
        }
        source_score = 3.0 if any(src in url or src in source for src in high_quality_sources) else 1.0
        
        # Content specificity (max 2 points)
        # Indicators: numbers, citations, structured info
        has_numbers = bool(re.search(r'\d+', content))
        has_quotes = "\"" in content or "'" in content
        has_links = "http" in url
        spec_score = (float(has_numbers) + float(has_quotes) + float(has_links) * 0.5) * 0.7
        
        # Content length bonus (max 2 points)
        length_score = min(2.0, len(content) / 1000.0)
        
        total = keyword_score + source_score + spec_score + length_score
        return min(10.0, total)

    async def _score_one_llm(
        self,
        query: str,
        chunk: dict,
        query_id: str,
    ) -> float:
        """Use LLM to score a single chunk."""
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

    async def _score_one(self, query: str, chunk: dict, query_id: str) -> float:
        """Legacy method for backward compatibility."""
        return await self._score_one_llm(query, chunk, query_id)
