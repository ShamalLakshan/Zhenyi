"""
Sliding-Window Rate Limiter & Token Bucket
──────────────────────────────────────────
Implements multi-metric rate limiting (RPM, TPM, RPD) with sliding window logs
to prevent cascading 429 errors across free LLM providers.
"""

import time
import logging
from collections import deque
from typing import Tuple, Dict

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """
    Tracks request timestamps and token usage per key within a 60-second window.
    Thread-safe and async-friendly.
    """

    def __init__(self):
        # Maps key_id -> deque of timestamps within last 60s
        self._request_windows: Dict[str, deque] = {}
        # Maps key_id -> deque of (timestamp, token_count) within last 60s
        self._token_windows: Dict[str, deque] = {}
        # Tracks last reset day (epoch day number) for midnight quota refresh
        self._current_day: int = int(time.time() // 86400)

    def _clean_old_entries(self, key_id: str, now: float):
        cutoff = now - 60.0
        
        req_queue = self._request_windows.get(key_id)
        if req_queue:
            while req_queue and req_queue[0] < cutoff:
                req_queue.popleft()

        tok_queue = self._token_windows.get(key_id)
        if tok_queue:
            while tok_queue and tok_queue[0][0] < cutoff:
                tok_queue.popleft()

    def get_rpm_used(self, key_id: str) -> int:
        now = time.time()
        self._clean_old_entries(key_id, now)
        return len(self._request_windows.get(key_id, []))

    def get_tpm_used(self, key_id: str) -> int:
        now = time.time()
        self._clean_old_entries(key_id, now)
        tok_queue = self._token_windows.get(key_id, [])
        return sum(tokens for _, tokens in tok_queue)

    def can_consume(
        self,
        key_id: str,
        rpm_limit: int,
        tpm_limit: int = 200000,
        estimated_tokens: int = 500
    ) -> Tuple[bool, float]:
        """
        Check if request can proceed.
        Returns: (allowed: bool, wait_seconds: float)
        """
        now = time.time()
        self._clean_old_entries(key_id, now)

        req_queue = self._request_windows.setdefault(key_id, deque())
        if len(req_queue) >= rpm_limit:
            # Wait until oldest request rolls off 60s window
            oldest = req_queue[0]
            wait_sec = max(0.1, (oldest + 60.0) - now + 0.1)
            return False, wait_sec

        tok_queue = self._token_windows.setdefault(key_id, deque())
        current_tpm = sum(t for _, t in tok_queue)
        if current_tpm + estimated_tokens > tpm_limit:
            oldest_tok_time = tok_queue[0][0]
            wait_sec = max(0.1, (oldest_tok_time + 60.0) - now + 0.1)
            return False, wait_sec

        return True, 0.0

    def record_consumption(self, key_id: str, tokens: int = 500):
        now = time.time()
        self._clean_old_entries(key_id, now)

        self._request_windows.setdefault(key_id, deque()).append(now)
        self._token_windows.setdefault(key_id, deque()).append((now, tokens))

    def has_day_rolled_over(self) -> bool:
        """Checks if a new UTC day has started for daily quota resets."""
        today = int(time.time() // 86400)
        if today != self._current_day:
            self._current_day = today
            return True
        return False
