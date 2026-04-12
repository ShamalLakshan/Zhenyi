"""
Wikipedia Scraper
──────────────────
Accesses Wikipedia via the MediaWiki API for general knowledge, background,
definitions, and factual information.

No API key required. Rate limit: ~5000 requests/day (shared pool).
Reliability: Extremely high (Wikimedia Foundation maintained).
"""

import asyncio
import logging
import requests
from typing import Optional

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "LLM Research Agent (github.com/council-bot)"
}


class WikipediaScraper(BaseScraper):

    def __init__(self, config: dict):
        super().__init__("wikipedia", config)

    async def _fetch(self, query: str) -> list[dict]:
        """
        Search Wikipedia for articles matching the query.
        Returns article summaries and links.
        """
        try:
            # Run the blocking requests in a thread pool
            results = await asyncio.to_thread(
                self._search_wikipedia,
                query,
                self.results_per_query
            )
            
            logger.info(f"[wikipedia] Found {len(results)} articles for: {query[:50]}")
            return results
        
        except Exception as e:
            logger.warning(f"[wikipedia] Error fetching articles: {e}")
            return []

    def _search_wikipedia(self, query: str, max_results: int) -> list[dict]:
        """
        Perform Wikipedia search and retrieve article summaries.
        Run in thread pool to avoid blocking.
        """
        try:
            # Step 1: Search for articles matching the query
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srwhat": "text",
                "srprop": "snippet|wordcount|timestamp",
                "srlimit": max_results,
                "format": "json",
            }
            
            search_resp = requests.get(
                WIKIPEDIA_API_URL,
                params=search_params,
                headers=HEADERS,
                timeout=self.timeout_seconds
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            
            search_results = search_data.get("query", {}).get("search", [])
            if not search_results:
                logger.debug(f"[wikipedia] No search results for: {query}")
                return []
            
            # Step 2: Get full article summaries for top results
            results = []
            article_titles = [r["title"] for r in search_results[:max_results]]
            
            for title in article_titles:
                try:
                    article_params = {
                        "action": "query",
                        "titles": title,
                        "prop": "extracts|info|pageimages",
                        "exintro": True,  # Only intro section
                        "explaintext": True,  # Plain text, no HTML
                        "format": "json",
                    }
                    
                    article_resp = requests.get(
                        WIKIPEDIA_API_URL,
                        params=article_params,
                        headers=HEADERS,
                        timeout=self.timeout_seconds
                    )
                    article_resp.raise_for_status()
                    article_data = article_resp.json()
                    
                    pages = article_data.get("query", {}).get("pages", {})
                    page_id = next(iter(pages.keys())) if pages else None
                    
                    if not page_id or page_id == "-1":
                        continue
                    
                    page = pages[page_id]
                    extract = page.get("extract", "")
                    
                    if not extract:
                        continue
                    
                    article_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    
                    results.append({
                        "source": "wikipedia",
                        "title": title,
                        "url": article_url,
                        "content": f"{title}\n\n{extract[:1500]}...",  # First 1500 chars
                    })
                    
                    if len(results) >= max_results:
                        break
                
                except Exception as e:
                    logger.debug(f"[wikipedia] Error fetching article '{title}': {e}")
                    continue
            
            return results
        
        except Exception as e:
            logger.error(f"[wikipedia] Search failed: {e}")
            return []
