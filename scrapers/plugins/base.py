"""
Modular Scraper Plugin Base
───────────────────────────
Extends BaseScraper with typed research items, metadata enrichment,
and integration with DocumentCleaner.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from scrapers.base_scraper import BaseScraper
from core.ingestion.cleaner import DocumentCleaner


@dataclass
class ResearchItem:
    """Standardized research item emitted by any scraper plugin."""
    source: str
    url: str
    title: str
    content: str
    authors: List[str] = field(default_factory=list)
    published_date: Optional[str] = None
    doi: Optional[str] = None
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to standard pipeline dictionary format."""
        return {
            "source": self.source,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "authors": self.authors,
            "published": self.published_date or "",
            "doi": self.doi or "",
            "score": self.score,
            "metadata": self.metadata,
        }


class ScraperPlugin(BaseScraper):
    """
    Base class for next-generation modular research plugins.
    Inherits circuit breaker and timeout enforcement from BaseScraper.
    """

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.cleaner = DocumentCleaner()

    def _normalise(self, raw: list[dict]) -> list[dict]:
        """Ensures consistent chunk formatting with title and source preservation."""
        out = []
        for item in raw:
            if isinstance(item, ResearchItem):
                d = item.to_dict()
            elif isinstance(item, dict):
                d = item
            else:
                continue

            content = str(d.get("content", "")).strip()
            if len(content) < 30:
                continue

            title = str(d.get("title", "")).strip() or content[:60]
            out.append({
                "source": d.get("source", self.name),
                "url": d.get("url", ""),
                "title": title[:200],
                "content": content[:4000],
                "authors": d.get("authors", []),
                "published": d.get("published", ""),
                "doi": d.get("doi", ""),
                "metadata": d.get("metadata", {}),
            })
        return out
