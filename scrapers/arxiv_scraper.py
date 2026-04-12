"""
arXiv Scraper
─────────────
Accesses the official arXiv API to fetch preprints and published papers across
physics, mathematics, computer science, and related fields.

No API key required. Rate limit: 3 requests/second.
Reliability: Extremely high (Cornell University maintained).
"""

import asyncio
import logging
from typing import Optional
import arxiv

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ArxivScraper(BaseScraper):

    def __init__(self, config: dict):
        super().__init__("arxiv", config)
        self.client = arxiv.Client()

    async def _fetch(self, query: str) -> list[dict]:
        """
        Fetch papers from arXiv matching the query.
        Returns structured results with title, authors, summary, PDF URL.
        """
        try:
            # Run the blocking arxiv search in a thread pool to avoid blocking
            search = await asyncio.to_thread(
                self._search_arxiv,
                query,
                self.results_per_query
            )
            
            results = []
            for paper in search:
                results.append({
                    "source": "arxiv",
                    "title": paper.title,
                    "url": paper.pdf_url,
                    "content": f"{paper.title}\n\nAuthors: {', '.join([a.name for a in paper.authors])}\n\nSummary:\n{paper.summary}",
                    "authors": [a.name for a in paper.authors],
                    "published": paper.published.isoformat() if paper.published else "",
                    "categories": paper.categories,
                })
                if len(results) >= self.results_per_query:
                    break
            
            logger.info(f"[arxiv] Found {len(results)} papers for: {query[:50]}")
            return results
        
        except Exception as e:
            logger.warning(f"[arxiv] Error fetching papers: {e}")
            return []

    def _search_arxiv(self, query: str, max_results: int) -> list:
        """
        Perform the actual arXiv search. Run in thread pool to avoid blocking.
        """
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
                sort_order=arxiv.SortOrder.Descending,
            )
            
            results = []
            for paper in self.client.results(search):
                results.append(paper)
                if len(results) >= max_results:
                    break
            
            return results
        except Exception as e:
            logger.error(f"[arxiv] Search failed: {e}")
            return []
