"""
Semantic Scholar Scraper Plugin
───────────────────────────────
Accesses the official Semantic Scholar Academic Graph API.
Completely free, no API key required for standard research queries.
Fields retrieved: title, abstract, authors, year, citation count, open-access PDF.
"""

import logging
import httpx
from typing import List, Dict, Any
from scrapers.plugins.base import ScraperPlugin, ResearchItem

logger = logging.getLogger(__name__)

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
USER_AGENT = "ZhenyiAcademicResearchBot/2.0 (mailto:research@zhenyi.local)"


class SemanticScholarScraper(ScraperPlugin):
    """Fetches high-signal academic papers, citations, and abstracts from Semantic Scholar."""

    def __init__(self, config: dict):
        super().__init__("semantic_scholar", config)
        self.api_key = config.get("api_key", "")

    async def _fetch(self, query: str) -> List[Dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        params = {
            "query": query,
            "limit": min(self.results_per_query, 15),
            "fields": "title,abstract,authors,year,citationCount,url,openAccessPdf,publicationDate",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            res = await client.get(API_URL, params=params, headers=headers)
            if res.status_code != 200:
                logger.warning(f"[semantic_scholar] API returned {res.status_code}: {res.text[:100]}")
                return []

            data = res.json()
            papers = data.get("data", [])
            items = []

            for paper in papers:
                title = paper.get("title", "")
                abstract = paper.get("abstract") or ""
                authors = [a.get("name") for a in paper.get("authors", []) if a.get("name")]
                year = paper.get("year")
                citations = paper.get("citationCount", 0)
                url = paper.get("url") or (paper.get("openAccessPdf", {}) or {}).get("url") or ""

                if not abstract and not title:
                    continue

                content_parts = [f"Title: {title}"]
                if authors:
                    content_parts.append(f"Authors: {', '.join(authors[:5])}")
                if year:
                    content_parts.append(f"Year: {year} (Citations: {citations})")
                if abstract:
                    content_parts.append(f"Abstract:\n{abstract}")

                items.append(ResearchItem(
                    source="semantic_scholar",
                    url=url,
                    title=title,
                    content="\n".join(content_parts),
                    authors=authors,
                    published_date=str(year) if year else None,
                    score=float(citations),
                    metadata={
                        "citation_count": citations,
                        "open_access_pdf": (paper.get("openAccessPdf") or {}).get("url"),
                    }
                ).to_dict())

            logger.info(f"[semantic_scholar] Found {len(items)} papers for: {query[:50]}")
            return items
