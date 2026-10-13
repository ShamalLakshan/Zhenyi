"""
Reddit Community Scraper Plugin
───────────────────────────────
Extracts discussions, engineering postmortems, troubleshooting threads,
and practitioner sentiment from Reddit's public JSON API.
100% free, no API key required for public endpoints with custom User-Agent.
"""

import logging
import httpx
from typing import List, Dict, Any
from scrapers.plugins.base import ScraperPlugin, ResearchItem

logger = logging.getLogger(__name__)

REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ZhenyiResearchBot/2.0 (Practitioner Inquiry)"


class RedditScraper(ScraperPlugin):
    """Scrapes developer and practitioner discussions across subreddits."""

    def __init__(self, config: dict):
        super().__init__("reddit", config)

    async def _fetch(self, query: str) -> List[Dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        params = {
            "q": query,
            "sort": "relevance",
            "limit": min(self.results_per_query, 12),
            "type": "link",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            res = await client.get(REDDIT_SEARCH_URL, params=params, headers=headers)
            if res.status_code != 200:
                logger.warning(f"[reddit] Search returned {res.status_code}")
                return []

            data = res.json()
            posts = data.get("data", {}).get("children", [])
            items = []

            for post in posts:
                p_data = post.get("data", {})
                title = p_data.get("title", "")
                selftext = p_data.get("selftext", "")
                subreddit = p_data.get("subreddit_name_prefixed", "")
                score = p_data.get("score", 0)
                comments_count = p_data.get("num_comments", 0)
                permalink = p_data.get("permalink", "")
                url = f"https://www.reddit.com{permalink}" if permalink else p_data.get("url", "")

                content_parts = [
                    f"Subreddit: {subreddit}",
                    f"Discussion: {title}",
                    f"Upvotes: {score} | Comments: {comments_count}",
                ]
                if selftext:
                    content_parts.append(f"Content:\n{selftext[:2000]}")

                items.append(ResearchItem(
                    source="reddit",
                    url=url,
                    title=f"[{subreddit}] {title}",
                    content="\n".join(content_parts),
                    score=float(score),
                    metadata={
                        "subreddit": subreddit,
                        "comments": comments_count,
                        "upvotes": score,
                    }
                ).to_dict())

            logger.info(f"[reddit] Found {len(items)} discussions for: {query[:50]}")
            return items
