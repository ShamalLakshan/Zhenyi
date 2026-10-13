"""
PubMed / NCBI Entrez Scraper Plugin
───────────────────────────────────
Accesses NCBI Entrez E-Utilities API for biomedical, genomic, pharmacology,
and clinical trial research from 35M+ citations.
100% free open REST API maintained by NIH / NLM.
"""

import logging
import httpx
from typing import List, Dict, Any
from scrapers.plugins.base import ScraperPlugin, ResearchItem

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
USER_AGENT = "ZhenyiBiomedicalBot/2.0 (mailto:biomed@zhenyi.local)"


class PubMedScraper(ScraperPlugin):
    """Fetches peer-reviewed medical and life sciences research from PubMed."""

    def __init__(self, config: dict):
        super().__init__("pubmed", config)

    async def _fetch(self, query: str) -> List[Dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            # 1. Search for PMIDs
            search_params = {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": min(self.results_per_query, 10),
                "sort": "relevance",
            }
            res = await client.get(ESEARCH_URL, params=search_params, headers=headers)
            if res.status_code != 200:
                logger.warning(f"[pubmed] ESearch returned {res.status_code}")
                return []

            id_list = res.json().get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return []

            # 2. Fetch summaries for PMIDs
            summary_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "json",
            }
            s_res = await client.get(ESUMMARY_URL, params=summary_params, headers=headers)
            if s_res.status_code != 200:
                return []

            summary_result = s_res.json().get("result", {})
            items = []

            for uid in id_list:
                doc = summary_result.get(uid)
                if not doc:
                    continue

                title = doc.get("title", "").rstrip(".")
                pubdate = doc.get("pubdate", "")
                source_journal = doc.get("source", "")
                authors = [a.get("name") for a in doc.get("authors", []) if a.get("name")]
                url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"

                content_parts = [f"Title: {title}"]
                if source_journal:
                    content_parts.append(f"Journal: {source_journal}")
                if pubdate:
                    content_parts.append(f"Publication Date: {pubdate}")
                if authors:
                    content_parts.append(f"Authors: {', '.join(authors[:5])}")
                content_parts.append(f"PMID: {uid}")

                items.append(ResearchItem(
                    source="pubmed",
                    url=url,
                    title=title,
                    content="\n".join(content_parts),
                    authors=authors,
                    published_date=pubdate,
                    metadata={"pmid": uid, "journal": source_journal}
                ).to_dict())

            logger.info(f"[pubmed] Found {len(items)} studies for: {query[:50]}")
            return items
