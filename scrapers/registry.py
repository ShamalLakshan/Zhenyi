"""
Scraper Registry
────────────────
Single place that owns all scraper instances.
The pipeline asks the registry to run scrapers by name — it never imports
individual scrapers directly. This means you can add a new scraper by:
  1. Creating scrapers/my_scraper.py (extend BaseScraper)
  2. Registering it here in _build()
  3. Adding it to agents.yaml under scrapers:

No changes needed anywhere else in the pipeline.
"""

import asyncio
import logging
from typing import Optional

from scrapers.hackernews import HackerNewsScraper
from scrapers.reddit import RedditScraper
from scrapers.web import WebScraper

logger = logging.getLogger(__name__)


class ScraperRegistry:

    def __init__(self, scraper_configs: dict):
        """
        scraper_configs: the 'scrapers' block from agents.yaml
        """
        self._scrapers: dict = {}
        self._build(scraper_configs)

    def _build(self, configs: dict):
        """Instantiate all scrapers. Each one handles its own availability."""
        scraper_classes = {
            "hackernews": HackerNewsScraper,
            "reddit":      RedditScraper,
            "web":         WebScraper,
            # ── Add new scrapers here ──────────────────────────────────────
            # "academic": AcademicScraper,
            # "stackoverflow": StackOverflowScraper,
        }

        for name, cls in scraper_classes.items():
            cfg = configs.get(name, {"enabled": True})
            try:
                instance = cls(cfg)
                self._scrapers[name] = instance
                status = "enabled" if instance.is_available else "disabled"
                logger.info(f"[registry] {name}: {status}")
            except Exception as e:
                logger.error(f"[registry] Failed to init {name}: {e}")

    async def run(self, names: list[str], query: str) -> list[dict]:
        """
        Run the requested scrapers concurrently.
        Each scraper is isolated — one failure does not affect others.
        Returns all chunks combined.
        """
        if not names:
            return []

        available = [
            name for name in names
            if name in self._scrapers and self._scrapers[name].is_available
        ]

        skipped = set(names) - set(available)
        if skipped:
            logger.info(f"[registry] Skipping unavailable scrapers: {skipped}")

        if not available:
            logger.warning("[registry] No available scrapers — returning empty")
            return []

        tasks = {
            name: self._scrapers[name].scrape(query)
            for name in available
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        all_chunks = []
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"[registry] {name} raised exception: {result}")
            elif isinstance(result, list):
                logger.info(f"[registry] {name}: {len(result)} chunks")
                all_chunks.extend(result)

        return all_chunks

    def status(self) -> dict:
        return {name: s.status() for name, s in self._scrapers.items()}
