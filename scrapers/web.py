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
import asyncio
import aiohttp
from urllib.parse import quote
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
    "Referer": DDG_LITE_URL,
}


class WebScraper(BaseScraper):

    def __init__(self, config: dict):
        super().__init__("web", config)

    async def _fetch(self, query: str) -> list[dict]:
        # Retry logic: 202 responses indicate async processing or rate limiting
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(headers=HEADERS) as session:
                    # Properly URL-encode the query parameter
                    encoded_query = quote(query)
                    url = f"{DDG_LITE_URL}?q={encoded_query}"
                    
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                        allow_redirects=True,
                    ) as resp:
                        if resp.status == 202:
                            # 202 = Accepted but not ready; retry after brief wait
                            if attempt < max_retries - 1:
                                await asyncio.sleep(0.5 * (attempt + 1))
                                continue
                            raise Exception(f"DDG returned status 202 (rate limited or async)")
                        elif resp.status != 200:
                            raise Exception(f"DDG returned status {resp.status}")
                        
                        html = await resp.text()
                        results = self._parse_ddg_html(html, query)
                        logger.info(f"[web] Found {len(results)} results for: {query[:50]}")
                        return results
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                raise Exception(f"DDG request timed out after {self.timeout_seconds}s")
        
        # All retries exhausted
        return []

    def _parse_ddg_html(self, html: str, query: str) -> list[dict]:
        """
        Extract result snippets from DuckDuckGo Lite HTML.
        Falls back to raw text extraction if HTML structure changes.
        DuckDuckGo Lite uses a simple HTML structure — look for result rows.
        """
        results = []

        # DDG Lite wraps results in divs or table cells
        # Look for patterns: heading (link text) followed by snippet
        
        # Pattern 1: Try extracting from common DDG result format
        # Results appear as: <a href="...">Title</a> followed by description
        lines = html.split('\n')
        current_url = None
        current_text = []

        for line in lines:
            # Extract URLs (external links, skip DDG internal links)
            url_match = re.search(r'href=["\']([^"\']+)["\']', line)
            if url_match:
                potential_url = url_match.group(1)
                # Skip internal DDG links
                if potential_url.startswith('http') and 'duckduckgo' not in potential_url:
                    if current_url and current_text:
                        # Save previous result
                        content = '\n'.join(current_text).strip()
                        if len(content) > 20:
                            results.append({
                                "source": "web",
                                "url": current_url,
                                "content": content,
                            })
                            if len(results) >= self.results_per_query:
                                break
                    current_url = potential_url
                    current_text = []
            elif current_url:
                # Accumulate description text for current result
                clean_line = re.sub(r"<[^>]+>", " ", line).strip()
                if clean_line and len(clean_line) > 5:
                    current_text.append(clean_line)

        # Don't forget last result
        if current_url and current_text and len(results) < self.results_per_query:
            content = '\n'.join(current_text).strip()
            if len(content) > 20:
                results.append({
                    "source": "web",
                    "url": current_url,
                    "content": content,
                })

        # Fallback if parsing found nothing: extract all readable text
        if not results:
            logger.debug("[web] HTML parsing found no results, using fallback text extraction")
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            text = re.sub(r"(Cookie|Accept|Privacy|Terms|Settings)", "", text, flags=re.IGNORECASE)
            
            # Only use if we have meaningful content
            if len(text) > 200:
                # Try to split into sentence-like chunks
                chunks = text.split('. ')[:5]
                content = '. '.join(chunks[:3]).strip()
                if len(content) > 50:
                    results.append({
                        "source": "web",
                        "url": DDG_LITE_URL,
                        "content": f"Search results for '{query}':\n{content}",
                    })

        return results
