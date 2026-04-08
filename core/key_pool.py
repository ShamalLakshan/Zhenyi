"""
Key Pool Scheduler
──────────────────
Manages API keys across all providers. Tracks per-key state (ready / cooldown /
exhausted), enforces rate limits, and selects the best available key on demand.

To add new keys: add the env var name to agents.yaml under the provider's
`keys` list, and add the actual key value to .env. No code changes needed.
"""

import os
import time
import logging
import yaml
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
from core.exceptions import NoAvailableKeysError, ConfigError

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class KeyState:
    """Tracks live usage state for a single API key."""
    provider: str
    env_var: str
    rpm_limit: int
    daily_limit: int

    # Runtime state (resets automatically)
    rpm_used: int = 0
    daily_used: int = 0
    window_start: float = field(default_factory=time.time)
    cooldown_until: float = 0.0
    consecutive_errors: int = 0

    @property
    def value(self) -> str:
        """Reads the key value from environment at call time — never stored."""
        return os.getenv(self.env_var, "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.value)

    @property
    def is_ready(self) -> bool:
        if not self.is_configured:
            return False
        self._reset_window_if_needed()
        return (
            time.time() > self.cooldown_until
            and self.rpm_used < self.rpm_limit
            and self.daily_used < self.daily_limit
        )

    @property
    def daily_remaining(self) -> int:
        return max(0, self.daily_limit - self.daily_used)

    @property
    def rpm_remaining(self) -> int:
        self._reset_window_if_needed()
        return max(0, self.rpm_limit - self.rpm_used)

    def _reset_window_if_needed(self):
        """Resets per-minute counters every 60 seconds."""
        if time.time() - self.window_start >= 60:
            self.rpm_used = 0
            self.window_start = time.time()

    def record_usage(self, estimated_tokens: int = 500):
        self._reset_window_if_needed()
        self.rpm_used += 1
        self.daily_used += estimated_tokens
        self.consecutive_errors = 0

    def set_cooldown(self, seconds: float = 65.0):
        """Put key in cooldown. Default 65s covers most rate-limit windows."""
        self.cooldown_until = time.time() + seconds
        logger.debug(f"Key {self.env_var} cooling down for {seconds:.0f}s")

    def record_error(self, is_rate_limit: bool = False):
        self.consecutive_errors += 1
        if is_rate_limit:
            self.set_cooldown(65.0)
        elif self.consecutive_errors >= 3:
            # Soft-disable after 3 non-rate-limit errors
            self.set_cooldown(300.0)
            logger.warning(f"Key {self.env_var} soft-disabled after 3 errors")

    def to_dict(self) -> dict:
        return {
            "env_var": self.env_var,
            "configured": self.is_configured,
            "ready": self.is_ready,
            "daily_remaining": self.daily_remaining,
            "rpm_remaining": self.rpm_remaining,
            "cooldown_seconds": max(0.0, self.cooldown_until - time.time()),
            "consecutive_errors": self.consecutive_errors,
        }


class KeyPool:
    """
    Central key manager. All LLM calls go through this.

    Usage:
        pool = KeyPool()
        key = pool.pick("groq")
        if key:
            result = call_api(key.value, ...)
            key.record_usage()
        else:
            # handle no key available
    """

    def __init__(self, config_path: str = "agents.yaml"):
        try:
            with open(config_path, encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {config_path}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {config_path}: {e}")

        self.pools: dict[str, list[KeyState]] = {}
        self._build_pools()
        self._log_pool_status()

    def _build_pools(self):
        providers = self.config.get("providers", {})
        for provider_name, p_cfg in providers.items():
            self.pools[provider_name] = []
            rpm = p_cfg.get("rpm_limit", 20)
            daily = p_cfg.get("daily_limit", 1000)
            for env_var in p_cfg.get("keys", []):
                self.pools[provider_name].append(KeyState(
                    provider=provider_name,
                    env_var=env_var,
                    rpm_limit=rpm,
                    daily_limit=daily,
                ))

    def _log_pool_status(self):
        for provider, keys in self.pools.items():
            configured = sum(1 for k in keys if k.is_configured)
            logger.info(f"Pool: {provider} — {configured}/{len(keys)} keys configured")

    # ─── Key Selection ────────────────────────────────────────────────────────

    def pick(self, provider: str) -> Optional[KeyState]:
        """
        Returns the best available key for a provider.
        'Best' = most daily quota remaining among all ready keys.
        Returns None if no key is available (caller must handle gracefully).
        """
        candidates = [
            k for k in self.pools.get(provider, [])
            if k.is_ready
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda k: k.daily_remaining)

    def pick_or_wait(self, provider: str, max_wait: float = 70.0) -> Optional[KeyState]:
        """
        Tries to pick a key. If none ready, returns the key with the shortest
        cooldown (caller can sleep if needed).
        """
        key = self.pick(provider)
        if key:
            return key
        # Return the key closest to becoming ready
        all_keys = [k for k in self.pools.get(provider, []) if k.is_configured]
        if not all_keys:
            return None
        return min(all_keys, key=lambda k: k.cooldown_until)

    # ─── Orchestrator Access ──────────────────────────────────────────────────

    def get_orchestrator_key(self) -> tuple[str, str, "KeyState"]:
        """
        Returns (api_key_value, model_name, key_state) for the orchestrator.
        key_state is returned so the caller can mark cooldown on 429.
        Raises NoAvailableKeysError if no Gemini key is available.
        """
        orch_cfg = self.config.get("orchestrator", {})
        provider = orch_cfg.get("provider", "gemini")
        model = orch_cfg.get("model", "gemini-2.0-flash")
        key = self.pick(provider)
        if key is None:
            raise NoAvailableKeysError(
                f"No available keys for orchestrator provider: {provider}"
            )
        return key.value, model, key

    # ─── Capabilities Snapshot ────────────────────────────────────────────────

    def get_capabilities_snapshot(self) -> dict:
        """
        Returns a live snapshot of all providers for the orchestrator to use
        when planning. Only includes providers with at least one ready key.
        """
        snapshot = {}
        for provider, keys in self.pools.items():
            ready = [k for k in keys if k.is_ready]
            if not ready:
                continue
            best = max(ready, key=lambda k: k.daily_remaining)
            p_cfg = self.config["providers"][provider]
            snapshot[provider] = {
                "available_keys": len(ready),
                "daily_remaining": best.daily_remaining,
                "rpm_remaining": best.rpm_remaining,
                "strengths": p_cfg.get("strengths", []),
                "models": p_cfg.get("models", {}),
                "base_url": p_cfg.get("base_url", ""),
            }
        return snapshot

    # ─── Config Helpers ───────────────────────────────────────────────────────

    def get_base_url(self, provider: str) -> str:
        return self.config["providers"].get(provider, {}).get("base_url", "")

    def get_threshold(self, name: str, default=None):
        return self.config.get("thresholds", {}).get(name, default)

    def get_scraper_config(self, scraper_name: str) -> dict:
        return self.config.get("scrapers", {}).get(scraper_name, {})

    # ─── Status / Debug ───────────────────────────────────────────────────────

    def status_report(self) -> dict:
        """Full status of all keys — useful for the UI and debugging."""
        report = {}
        for provider, keys in self.pools.items():
            report[provider] = [k.to_dict() for k in keys]
        return report

    def total_configured_keys(self) -> int:
        return sum(
            1 for keys in self.pools.values()
            for k in keys if k.is_configured
        )
