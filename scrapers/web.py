"""
Web Scraper
───────────
General-purpose web scraper using the DuckDuckGo Lite search page and aiohttp.
No API keys required. Scrapes search result snippets.

Limitations:
- DuckDuckGo Lite HTML may change — the scraper handles this gracefully
- No JavaScript rendering — static HTML only
- Rate limited by DuckDuckGo if called too frequently (circuit breaker handles this)
"""

import re
import logging
import aiohttp
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class WebScraper(BaseScraper):

    def __init__(self, config: dict):
        super().__init__("web", config)

    async def _fetch(self, query: str) -> list[dict]:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # DuckDuckGo Lite uses simple GET requests with ?q= parameter
            url = f"{DDG_LITE_URL}?q={query}"
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"DDG returned status {resp.status}")
                html = await resp.text()

        results = self._parse_ddg_html(html, query)
        logger.info(f"[web] Found {len(results)} results for: {query[:50]}")
        return results

    def _parse_ddg_html(self, html: str, query: str) -> list[dict]:
        """
        Extract result snippets from DuckDuckGo Lite HTML.
        Falls back to raw text extraction if HTML structure changes.
        """
        results = []

        # Try to extract links and snippets from the HTML table structure
        # DDG Lite uses a simple table layout
        link_pattern = re.compile(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', re.IGNORECASE
        )
        snippet_pattern = re.compile(
            r'<td[^>]*class=["\'][^"\']*result-snippet[^"\']*["\'][^>]*>(.*?)</td>',
            re.IGNORECASE | re.DOTALL
        )

        links = link_pattern.findall(html)
        snippets_raw = snippet_pattern.findall(html)

        # Clean snippets
        snippets = []
        for s in snippets_raw:
            cleaned = re.sub(r"<[^>]+>", " ", s)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if len(cleaned) > 30:
                snippets.append(cleaned)

        # Pair links with snippets
        real_links = [
            (url, text) for url, text in links
            if url.startswith("http") and "duckduckgo" not in url
        ]

        for i, (url, link_text) in enumerate(real_links[:self.results_per_query]):
            snippet = snippets[i] if i < len(snippets) else link_text
            content = f"{link_text}\n{snippet}".strip()
            if len(content) < 20:
                continue
            results.append({
                "source": "web",
                "url": url,
                "content": content,
            })

        # If parsing failed, use a broad text extraction as fallback
        if not results:
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 100:
                results.append({
                    "source": "web",
                    "url": DDG_LITE_URL,
                    "content": f"Search results for '{query}':\n{text[:2000]}",
                })

        return results
