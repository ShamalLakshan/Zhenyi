"""
HackerNews Scraper
──────────────────
Uses the Algolia HN Search API — no credentials required.

The Algolia search engine works best with short, precise keyword queries.
Long natural-language sentences return 0 results. This scraper automatically:
  1. Distills the query to the 3-5 most important keywords
  2. Tries the distilled query first
  3. Falls back to each individual keyword if the full query returns nothing
  4. Merges and deduplicates results across all attempts
"""

import re
import aiohttp
import logging
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

# Common words that add no search value
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "me", "my", "i",
    "you", "your", "we", "our", "they", "their", "it", "its", "this",
    "that", "these", "those", "what", "which", "who", "how", "when",
    "where", "why", "all", "any", "give", "find", "get", "tell", "show",
    "name", "list", "about", "information", "good", "best", "please",
    "need", "want", "looking", "search", "more", "most", "some", "know",
}


def _distill_query(query: str, max_keywords: int = 5) -> list[str]:
    """
    Extract the most important keywords from a long query string.
    Returns a list: [full_distilled, keyword1, keyword2, ...]
    so the scraper can try them in order.
    """
    # Lowercase, remove punctuation
    cleaned = re.sub(r"[^\w\s]", " ", query.lower())
    words = cleaned.split()

    # Remove stopwords and short words
    keywords = [
        w for w in words
        if w not in STOPWORDS and len(w) > 2
    ]

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)

    # Build search queries to try in order:
    # 1. Top N keywords joined (most specific)
    # 2. Individual keywords (broadest fallback)
    top = unique[:max_keywords]
    queries = []
    if top:
        queries.append(" ".join(top))          # e.g. "capacitors transistors electronics"
    for kw in top[:3]:                         # individual fallbacks
        if kw not in queries:
            queries.append(kw)

    return queries if queries else [query[:100]]


class HackerNewsScraper(BaseScraper):

    def __init__(self, config: dict):
        super().__init__("hackernews", config)

    async def _fetch(self, query: str) -> list[dict]:
        search_queries = _distill_query(query, max_keywords=5)
        logger.info(
            f"[hackernews] Original: '{query[:60]}' "
            f"→ trying: {search_queries}"
        )

        seen_ids = set()
        results = []

        async with aiohttp.ClientSession() as session:
            for sq in search_queries:
                batch = await self._search_one(session, sq)
                for item in batch:
                    item_id = item.get("_id", item.get("url", ""))
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        results.append(item)

                if len(results) >= self.results_per_query:
                    break  # have enough — stop trying more queries

        if not results:
            logger.warning(
                f"[hackernews] 0 results after trying all distilled queries: {search_queries}. "
                f"This usually means the topic has no HN coverage."
            )
        else:
            logger.info(f"[hackernews] {len(results)} results for: {query[:50]}")

        return results[:self.results_per_query]

    async def _search_one(self, session: aiohttp.ClientSession, sq: str) -> list[dict]:
        """Run a single Algolia search and return raw result dicts."""
        params = {
            "query": sq,
            "tags": "story",
            "hitsPerPage": self.results_per_query,
        }
        try:
            async with session.get(
                HN_SEARCH_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[hackernews] API status {resp.status} for query '{sq}'")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.warning(f"[hackernews] Request failed for '{sq}': {e}")
            return []

        hits = data.get("hits", [])
        results = []
        for hit in hits:
            title = hit.get("title", "")
            body = hit.get("story_text") or ""
            content = f"{title}\n\n{body}".strip()

            if len(content) < 20:
                content = title

            item_id = hit.get("objectID", "")
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={item_id}"

            results.append({
                "_id": item_id,
                "source": "hackernews",
                "url": url,
                "content": content,
                "score": hit.get("points", 0),
                "comments": hit.get("num_comments", 0),
            })

        logger.debug(f"[hackernews] '{sq}' → {len(results)} hits")
        return results
