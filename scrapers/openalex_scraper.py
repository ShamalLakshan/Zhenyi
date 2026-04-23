"""
OpenAlex Scraper
────────────────
Accesses OpenAlex API for scholarly article metadata, author info, and research trends.
No API key required. Rate limit: 100,000 requests/month (shared pool).
Reliability: Very High (Community-maintained, backed by research institutions).

OpenAlex is a free, open index of scholarly metadata maintained by the University of
Illinois and Scholarly Kitchen. Much faster than arXiv for finding related work and
institutional research.
"""

import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

OPENALEX_API_URL = "https://api.openalex.org/works"
HEADERS = {
    "User-Agent": "Zhenyi Research Agent (github.com/zhenyi-research)",
}


class OpenalexScraper(BaseScraper):
    """Search OpenAlex for scholarly articles and metadata."""

    def __init__(self, config: dict):
        super().__init__("openalex", config)

    async def _fetch(self, query: str) -> list[dict]:
        """
        Search OpenAlex for research articles and metadata.
        """
        try:
            results = await asyncio.to_thread(
                self._search_openalex,
                query,
                self.results_per_query
            )
            logger.info(f"[openalex] Found {len(results)} articles for: {query[:50]}")
            return results
        
        except Exception as e:
            logger.warning(f"[openalex] Error searching: {e}")
            return []

    def _search_openalex(self, query: str, max_results: int) -> list[dict]:
        """
        Search OpenAlex API for scholarly articles.
        Run in thread pool to avoid blocking.
        """
        try:
            import requests
            
            # Build search query
            params = {
                "search": query,
                "per_page": max_results,
                "sort": "cited_by_count:desc",  # Most cited first
            }
            
            resp = requests.get(
                OPENALEX_API_URL,
                params=params,
                headers=HEADERS,
                timeout=self.timeout_seconds
            )
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            for work in data.get("results", []):
                try:
                    # Extract key fields
                    title = work.get("title", "")
                    doi = work.get("doi", "")
                    url = doi if doi else work.get("best_oa_location", {}).get("url", "")
                    
                    if not url:
                        url = f"https://openalex.org/{work.get('id', '').split('/')[-1]}"
                    
                    # Authors
                    authors = []
                    for auth_info in work.get("authorships", [])[:5]:  # Top 5 authors
                        author_name = auth_info.get("author", {}).get("display_name", "")
                        if author_name:
                            authors.append(author_name)
                    
                    # Publication year
                    year = work.get("publication_year", "")
                    
                    # Abstract/summary (might be available)
                    abstract = work.get("abstract_inverted_index", {})
                    # Note: abstract_inverted_index needs to be reconstructed; skip for simplicity
                    summary = f"Published {year}. {len(authors)} authors."
                    
                    # Citation count
                    citations = work.get("cited_by_count", 0)
                    
                    content = f"{title}\n\nPublications: {year}\nAuthors: {', '.join(authors[:3])}\nCitations: {citations}"
                    
                    results.append({
                        "source": "openalex",
                        "title": title,
                        "url": url,
                        "content": content,
                        "authors": authors,
                        "published": str(year),
                        "citations": citations,
                    })
                
                except Exception as e:
                    logger.debug(f"[openalex] Error parsing work: {e}")
                    continue
            
            return results
        
        except Exception as e:
            logger.error(f"[openalex] Search failed: {e}")
            return []
