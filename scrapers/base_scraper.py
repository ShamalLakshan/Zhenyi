"""
Base Scraper
────────────
All scrapers inherit from this. Provides:
- Circuit breaker: after 3 consecutive failures, scraper is disabled for the
  rest of the session. Re-enables after RECOVERY_WAIT_SECONDS.
- Standardised return format: list of {source, url, content} dicts.
- Timeout enforcement.
- All failures are logged, never raised — returns [] on any error.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

FAILURE_THRESHOLD = 3         # failures before circuit opens
RECOVERY_WAIT_SECONDS = 300   # 5 minutes before retry after circuit opens


class BaseScraper(ABC):
    """
    Abstract base for all scrapers.
    Subclasses implement _fetch() only — circuit breaker wraps it automatically.
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.enabled = config.get("enabled", True)
        self.results_per_query = config.get("results_per_query", 10)
        self.timeout_seconds = config.get("timeout_seconds", 10)

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_since: float = 0.0
        self._circuit_open = False

    @property
    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self._circuit_open:
            # Check if recovery window has passed
            if time.time() - self._circuit_open_since > RECOVERY_WAIT_SECONDS:
                self._circuit_open = False
                self._consecutive_failures = 0
                logger.info(f"[{self.name}] Circuit closed after recovery wait")
                return True
            return False
        return True

    async def scrape(self, query: str) -> list[dict]:
        """
        Public entry point. Wraps _fetch() with circuit breaker and timeout.
        Always returns a list — empty on any failure.
        """
        if not self.is_available:
            logger.debug(f"[{self.name}] Skipped — not available (circuit={self._circuit_open})")
            return []

        try:
            results = await asyncio.wait_for(
                self._fetch(query),
                timeout=self.timeout_seconds
            )
            self._on_success()
            return self._normalise(results)
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timed out after {self.timeout_seconds}s")
            self._on_failure()
            return []
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")
            self._on_failure()
            return []

    @abstractmethod
    async def _fetch(self, query: str) -> list[dict]:
        """
        Subclasses implement this. Should return raw dicts with at minimum:
        {url: str, content: str}
        source will be added by normalise().
        """
        raise NotImplementedError

    def _normalise(self, raw: list[dict]) -> list[dict]:
        """Ensures every chunk has source, url, and content fields."""
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if len(content) < 30:
                continue
            out.append({
                "source": item.get("source", self.name),
                "url": item.get("url", ""),
                "content": content[:3000],
            })
        return out

    def _on_success(self):
        self._consecutive_failures = 0

    def _on_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= FAILURE_THRESHOLD:
            self._circuit_open = True
            self._circuit_open_since = time.time()
            logger.warning(
                f"[{self.name}] Circuit OPEN after {FAILURE_THRESHOLD} consecutive failures. "
                f"Will retry in {RECOVERY_WAIT_SECONDS}s."
            )

    def status(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "available": self.is_available,
            "circuit_open": self._circuit_open,
            "consecutive_failures": self._consecutive_failures,
        }
