"""
Jina AI Reader & Search Plugin
──────────────────────────────
Accesses Jina AI Reader (https://r.jina.ai/<url>) and Jina Search (https://s.jina.ai/<query>).
100% free proxy that returns pristine, LLM-ready markdown from web queries without
HTML boilerplate, ads, cookie banners, or paywalls.
"""

import logging
import httpx
from typing import List, Dict, Any
from scrapers.plugins.base import ScraperPlugin, ResearchItem

logger = logging.getLogger(__name__)

JINA_SEARCH_PREFIX = "https://s.jina.ai/"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ZhenyiResearchBot/2.0 (Jina Reader)"


class JinaReaderScraper(ScraperPlugin):
    """Fetches high-quality web markdown via Jina Reader engine."""

    def __init__(self, config: dict):
        super().__init__("jina_reader", config)

    async def _fetch(self, query: str) -> List[Dict[str, Any]]:
        target_url = f"{JINA_SEARCH_PREFIX}{query}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/plain, text/markdown",
            "X-No-Cache": "true",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            res = await client.get(target_url, headers=headers)
            if res.status_code != 200:
                logger.warning(f"[jina_reader] Search returned {res.status_code}")
                return []

            text = res.text
            if not text or len(text.strip()) < 50:
                return []

            # Jina search returns markdown sections formatted like:
            # Title: ...
            # URL Source: ...
            # Markdown Content: ...
            # Let's chunk the returned sections
            sections = text.split("\n------------------------------------------------\n")
            if len(sections) <= 1:
                sections = text.split("Title:")

            items = []
            for sec in sections[:self.results_per_query]:
                sec_text = sec.strip()
                if len(sec_text) < 50:
                    continue

                # Extract title and URL if available
                title = f"Jina Search: {query}"
                url = ""
                for line in sec_text.splitlines()[:5]:
                    if line.startswith("Title:") or line.startswith("# "):
                        title = line.replace("Title:", "").replace("# ", "").strip()
                    elif "URL Source:" in line or "http" in line:
                        parts = line.split("http")
                        if len(parts) > 1:
                            url = "http" + parts[1].strip()

                items.append(ResearchItem(
                    source="jina_reader",
                    url=url or f"https://s.jina.ai/{query}",
                    title=title[:120],
                    content=sec_text[:3500],
                    score=1.0,
                    metadata={"proxy": "jina.ai"}
                ).to_dict())

            logger.info(f"[jina_reader] Generated {len(items)} markdown chunks for: {query[:50]}")
            return items
