"""
DuckDuckGo Search Scraper (via duckduckgo-search library)
──────────────────────────────────────────────────────────
Fast, anonymous web search via DuckDuckGo's unofficial API.
No API key required. Rate limit: undocumented but generous (~100+ req/min).
Reliability: Medium-High (depends on DuckDuckGo infrastructure).

This scraper supplements web.py which uses DDG Lite HTML directly.
The ddgs library is more reliable for edge cases and provides better structure.
"""

import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class DdgsScraper(BaseScraper):
    """Search via DuckDuckGo using the duckduckgo-search library."""

    def __init__(self, config: dict):
        super().__init__("ddgs", config)
        # Lazy import to avoid hard dependency
        self.ddgs = None

    async def _fetch(self, query: str) -> list[dict]:
        """Search DuckDuckGo and return results."""
        try:
            results = await asyncio.to_thread(
                self._search_ddgs,
                query,
                self.results_per_query
            )
            logger.info(f"[ddgs] Found {len(results)} results for: {query[:50]}")
            return results
        
        except Exception as e:
            logger.warning(f"[ddgs] Error searching: {e}")
            return []

    def _search_ddgs(self, query: str, max_results: int) -> list[dict]:
        """
        Perform DuckDuckGo search.
        Run in thread pool to avoid blocking.
        """
        try:
            # Lazy import (use new 'ddgs' package name)
            try:
                from ddgs import DDGS
            except ImportError:
                # Fallback for older installations
                from duckduckgo_search import DDGS
            
            results = []
            try:
                with DDGS(timeout=self.timeout_seconds) as ddgs:
                    search_results = list(
                        ddgs.text(query, max_results=max_results)
                    )
                    
                    for item in search_results:
                        results.append({
                            "source": "ddgs",
                            "title": item.get("title", ""),
                            "url": item.get("href", ""),
                            "content": item.get("body", ""),
                        })
            
            except Exception as e:
                logger.warning(f"[ddgs] Search failed: {e}")
                return []
            
            return results
        
        except Exception as e:
            logger.error(f"[ddgs] Initialization failed: {e}")
            return []
