"""
Crossref Scraper Plugin
───────────────────────
Queries Crossref REST API for 140M+ academic journal articles, conference papers,
and books with official DOIs and publisher metadata.
100% free polite pool with zero API keys required.
"""

import logging
import httpx
from typing import List, Dict, Any
from scrapers.plugins.base import ScraperPlugin, ResearchItem

logger = logging.getLogger(__name__)

API_URL = "https://api.crossref.org/works"
USER_AGENT = "ZhenyiResearchStudio/2.0 (mailto:research@zhenyi.local)"


class CrossrefScraper(ScraperPlugin):
    """Fetches publication metadata, DOIs, abstracts, and citations from Crossref."""

    def __init__(self, config: dict):
        super().__init__("crossref", config)

    async def _fetch(self, query: str) -> List[Dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        params = {
            "query": query,
            "rows": min(self.results_per_query, 12),
            "sort": "relevance",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            res = await client.get(API_URL, params=params, headers=headers)
            if res.status_code != 200:
                logger.warning(f"[crossref] API returned {res.status_code}")
                return []

            data = res.json()
            items_raw = data.get("message", {}).get("items", [])
            items = []

            for item in items_raw:
                titles = item.get("title", [])
                title = titles[0] if titles else "Untitled Work"
                doi = item.get("DOI", "")
                url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
                journal = (item.get("container-title") or [""])[0]
                cited_by = item.get("is-referenced-by-count", 0)

                authors = []
                for author in item.get("author", []):
                    given = author.get("given", "")
                    family = author.get("family", "")
                    name = f"{given} {family}".strip()
                    if name:
                        authors.append(name)

                abstract = item.get("abstract", "")
                if abstract.startswith("<jats:p>"):
                    abstract = abstract.replace("<jats:p>", "").replace("</jats:p>", "").strip()

                content_parts = [f"Title: {title}"]
                if journal:
                    content_parts.append(f"Journal / Venue: {journal}")
                if authors:
                    content_parts.append(f"Authors: {', '.join(authors[:5])}")
                if doi:
                    content_parts.append(f"DOI: {doi} (Citations: {cited_by})")
                if abstract:
                    content_parts.append(f"Abstract:\n{abstract}")

                items.append(ResearchItem(
                    source="crossref",
                    url=url,
                    title=title,
                    content="\n".join(content_parts),
                    authors=authors,
                    doi=doi,
                    score=float(cited_by),
                    metadata={
                        "journal": journal,
                        "citation_count": cited_by,
                    }
                ).to_dict())

            logger.info(f"[crossref] Found {len(items)} works for: {query[:50]}")
            return items
