"""
Reddit Scraper
──────────────
Uses the PRAW library with Reddit's official API.
Requires REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET in .env.

If credentials are missing, the scraper disables itself gracefully —
the rest of the pipeline continues without Reddit data.

To set up:
  1. Go to https://www.reddit.com/prefs/apps
  2. Create a "script" app
  3. Copy client_id and client_secret to .env
"""

import os
import asyncio
import logging
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class RedditScraper(BaseScraper):

    def __init__(self, config: dict):
        super().__init__("reddit", config)
        self.subreddits = config.get("subreddits", [])

        # Check credentials at init — disable cleanly if missing
        self._client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        self._client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        self._user_agent = os.getenv("REDDIT_USER_AGENT", "council_bot/1.0")

        if not self._client_id or not self._client_secret:
            logger.info(
                "[reddit] No credentials found in .env — scraper disabled. "
                "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to enable."
            )
            self.enabled = False

    async def _fetch(self, query: str) -> list[dict]:
        # Run synchronous PRAW in thread pool to avoid blocking
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: str) -> list[dict]:
        try:
            import praw
        except ImportError:
            logger.warning("[reddit] praw not installed. Run: pip install praw")
            return []

        reddit = praw.Reddit(
            client_id=self._client_id,
            client_secret=self._client_secret,
            user_agent=self._user_agent,
            ratelimit_seconds=30,
        )

        results = []
        try:
            if self.subreddits:
                # Search specific subreddits
                for sub_name in self.subreddits[:3]:
                    sub = reddit.subreddit(sub_name)
                    for post in sub.search(query, limit=self.results_per_query // 2, sort="relevance"):
                        results.append(self._post_to_dict(post))
            else:
                # Search all of Reddit
                for post in reddit.subreddit("all").search(
                    query, limit=self.results_per_query, sort="relevance", time_filter="year"
                ):
                    results.append(self._post_to_dict(post))
        except Exception as e:
            logger.warning(f"[reddit] Search error: {e}")

        logger.info(f"[reddit] Found {len(results)} results for: {query[:50]}")
        return results

    def _post_to_dict(self, post) -> dict:
        content = f"{post.title}\n\n{post.selftext or ''}".strip()
        return {
            "source": "reddit",
            "url": f"https://reddit.com{post.permalink}",
            "content": content,
            "subreddit": str(post.subreddit),
            "score": post.score,
        }
