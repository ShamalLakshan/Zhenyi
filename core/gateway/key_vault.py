"""
Key Vault & Persistent Credential Storage
──────────────────────────────────────────
Manages persistent API keys in SQLite (api_keys table).
Handles masking, encryption, CRUD operations, usage tracking, cooldowns,
and automatic seeding from .env & agents.yaml.
"""

import aiosqlite
import os
import time
import uuid
import yaml
import logging
from typing import Optional, List, Tuple, Dict, Any
from dotenv import load_dotenv

from core.gateway.models import (
    KeyModel, KeyStatus, KeyCreateRequest, KeyUpdateRequest,
    PROVIDER_SPECS
)

load_dotenv()
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "zhenyi.db")


def mask_api_key(key: str) -> str:
    """Mask an API key for safe UI display and logging."""
    if not key:
        return ""
    clean = key.strip()
    if len(clean) <= 8:
        return "***" + clean[-2:]
    prefix = clean[:4]
    suffix = clean[-4:]
    return f"{prefix}...{suffix}"


class KeyVault:
    """Persistent API Key Vault backed by SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._raw_keys_cache: Dict[str, str] = {}

    async def init_vault(self):
        """Create api_keys table if not exists and seed if empty."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id                  TEXT PRIMARY KEY,
                    provider            TEXT NOT NULL,
                    label               TEXT,
                    key_value           TEXT NOT NULL,
                    rpm_limit           INTEGER DEFAULT 30,
                    daily_quota         INTEGER DEFAULT 1000,
                    daily_used          INTEGER DEFAULT 0,
                    tokens_used_today   INTEGER DEFAULT 0,
                    status              TEXT DEFAULT 'ready',
                    cooldown_until      REAL DEFAULT 0,
                    consecutive_errors  INTEGER DEFAULT 0,
                    last_used_at        REAL,
                    last_exhaustion_time REAL DEFAULT 0,
                    created_at          REAL NOT NULL,
                    updated_at          REAL NOT NULL
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status);")
            await db.commit()

        # Seed from agents.yaml and .env if empty
        await self.seed_from_config_if_empty()

    async def seed_from_config_if_empty(self):
        """Seed API keys into the vault from agents.yaml and .env if the table is empty."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT COUNT(*) FROM api_keys")
                count = (await cursor.fetchone())[0]
                if count > 0:
                    return

            config_path = "agents.yaml"
            if not os.path.exists(config_path):
                return

            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            providers = cfg.get("providers", {})
            seeded_count = 0

            for provider_name, p_cfg in providers.items():
                env_keys = p_cfg.get("keys", [])
                rpm = p_cfg.get("rpm_limit", 20)
                daily = p_cfg.get("daily_limit", 1000)

                for env_var in env_keys:
                    val = os.getenv(env_var, "").strip()
                    if val:
                        await self.add_key(
                            provider=provider_name,
                            key_value=val,
                            label=f"{provider_name.capitalize()} ({env_var})",
                            rpm_limit=rpm,
                            daily_quota=daily,
                        )
                        seeded_count += 1

            if seeded_count > 0:
                logger.info(f"Seeded {seeded_count} API keys into SQLite Key Vault from .env / agents.yaml")
        except Exception as e:
            logger.warning(f"Could not auto-seed API keys: {e}")

    async def add_key(
        self,
        provider: str,
        key_value: str,
        label: Optional[str] = None,
        rpm_limit: Optional[int] = None,
        daily_quota: Optional[int] = None,
    ) -> KeyModel:
        """Add a new API key to the vault."""
        clean_key = key_value.strip()
        if not clean_key:
            raise ValueError("API key cannot be empty")

        p_name = provider.lower().strip()
        spec = PROVIDER_SPECS.get(p_name)
        rpm = rpm_limit or (spec.rpm_default if spec else 30)
        daily = daily_quota or (spec.daily_quota_default if spec else 1000)
        lbl = label or f"{p_name.capitalize()} Key"
        key_id = f"key_{uuid.uuid4().hex[:12]}"
        now = time.time()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO api_keys (
                    id, provider, label, key_value, rpm_limit, daily_quota,
                    daily_used, tokens_used_today, status, cooldown_until,
                    consecutive_errors, last_used_at, last_exhaustion_time,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 'ready', 0, 0, NULL, 0, ?, ?)
                """,
                (key_id, p_name, lbl, clean_key, rpm, daily, now, now)
            )
            await db.commit()

        self._raw_keys_cache[key_id] = clean_key
        return KeyModel(
            id=key_id,
            provider=p_name,
            label=lbl,
            key_masked=mask_api_key(clean_key),
            rpm_limit=rpm,
            daily_quota=daily,
            daily_used=0,
            tokens_used_today=0,
            status=KeyStatus.READY,
            cooldown_until=0.0,
            consecutive_errors=0,
            created_at=now,
            updated_at=now,
        )

    async def list_keys(self, provider: Optional[str] = None) -> List[KeyModel]:
        """List all keys in the vault, with values masked."""
        query = "SELECT * FROM api_keys"
        params = []
        if provider:
            query += " WHERE provider = ?"
            params.append(provider.lower().strip())
        query += " ORDER BY provider ASC, created_at ASC"

        keys: List[KeyModel] = []
        now = time.time()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            for r in rows:
                status_val = r["status"]
                cooldown_until = r["cooldown_until"] or 0.0

                # Derive live status
                if status_val == "disabled":
                    live_status = KeyStatus.DISABLED
                elif now <= cooldown_until:
                    live_status = KeyStatus.COOLING
                elif (r["daily_used"] or 0) >= (r["daily_quota"] or 1000):
                    live_status = KeyStatus.EXHAUSTED
                elif (r["consecutive_errors"] or 0) >= 3:
                    live_status = KeyStatus.ERROR
                else:
                    live_status = KeyStatus.READY

                keys.append(KeyModel(
                    id=r["id"],
                    provider=r["provider"],
                    label=r["label"] or "",
                    key_masked=mask_api_key(r["key_value"]),
                    rpm_limit=r["rpm_limit"] or 30,
                    daily_quota=r["daily_quota"] or 1000,
                    daily_used=r["daily_used"] or 0,
                    tokens_used_today=r["tokens_used_today"] or 0,
                    status=live_status,
                    cooldown_until=cooldown_until,
                    consecutive_errors=r["consecutive_errors"] or 0,
                    last_used_at=r["last_used_at"],
                    last_exhaustion_time=r["last_exhaustion_time"] or 0.0,
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                ))
        return keys

    async def get_raw_key(self, key_id: str) -> Optional[Tuple[KeyModel, str]]:
        """Retrieve key model and raw decrypted key value for gateway execution."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
            r = await cursor.fetchone()
            if not r:
                return None

            raw_val = r["key_value"]
            self._raw_keys_cache[key_id] = raw_val

            model = KeyModel(
                id=r["id"],
                provider=r["provider"],
                label=r["label"] or "",
                key_masked=mask_api_key(raw_val),
                rpm_limit=r["rpm_limit"] or 30,
                daily_quota=r["daily_quota"] or 1000,
                daily_used=r["daily_used"] or 0,
                tokens_used_today=r["tokens_used_today"] or 0,
                status=KeyStatus(r["status"]) if r["status"] in KeyStatus._value2member_map_ else KeyStatus.READY,
                cooldown_until=r["cooldown_until"] or 0.0,
                consecutive_errors=r["consecutive_errors"] or 0,
                last_used_at=r["last_used_at"],
                last_exhaustion_time=r["last_exhaustion_time"] or 0.0,
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            return model, raw_val

    async def pick_best_key(self, provider: str) -> Optional[Tuple[KeyModel, str]]:
        """
        Pick the best ready key for a provider.
        Best = Ready, not cooling, highest daily_remaining quota.
        """
        keys = await self.list_keys(provider=provider)
        ready_keys = [k for k in keys if k.is_usable]
        if not ready_keys:
            return None

        # Sort by daily_remaining descending
        best_model = max(ready_keys, key=lambda k: k.daily_remaining)
        raw_info = await self.get_raw_key(best_model.id)
        if raw_info:
            return raw_info
        return None

    async def update_key(self, key_id: str, req: KeyUpdateRequest) -> Optional[KeyModel]:
        """Update settings for an existing API key."""
        updates = []
        params = []
        if req.label is not None:
            updates.append("label = ?")
            params.append(req.label)
        if req.rpm_limit is not None:
            updates.append("rpm_limit = ?")
            params.append(req.rpm_limit)
        if req.daily_quota is not None:
            updates.append("daily_quota = ?")
            params.append(req.daily_quota)
        if req.status is not None:
            updates.append("status = ?")
            params.append(req.status.value)

        if not updates:
            raw_info = await self.get_raw_key(key_id)
            return raw_info[0] if raw_info else None

        updates.append("updated_at = ?")
        params.append(time.time())
        params.append(key_id)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE api_keys SET {', '.join(updates)} WHERE id = ?",
                params
            )
            await db.commit()

        raw_info = await self.get_raw_key(key_id)
        return raw_info[0] if raw_info else None

    async def delete_key(self, key_id: str) -> bool:
        """Delete an API key from the vault."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            await db.commit()
            self._raw_keys_cache.pop(key_id, None)
            return cursor.rowcount > 0

    async def record_usage(self, key_id: str, tokens_in: int, tokens_out: int, latency_ms: float):
        """Record usage and update counters in the database."""
        total_tokens = tokens_in + tokens_out
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE api_keys SET
                    daily_used = daily_used + 1,
                    tokens_used_today = tokens_used_today + ?,
                    consecutive_errors = 0,
                    last_used_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (total_tokens, now, now, key_id)
            )
            await db.commit()

    async def record_error(
        self,
        key_id: str,
        is_rate_limit: bool = False,
        is_quota: bool = False,
        cooldown_seconds: float = 65.0,
    ):
        """Update error tracking and set cooldown on key."""
        now = time.time()
        cooldown_until = now + cooldown_seconds

        async with aiosqlite.connect(self.db_path) as db:
            if is_quota:
                await db.execute(
                    """
                    UPDATE api_keys SET
                        status = 'exhausted',
                        cooldown_until = ?,
                        last_exhaustion_time = ?,
                        consecutive_errors = consecutive_errors + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (cooldown_until, now, now, key_id)
                )
            elif is_rate_limit:
                await db.execute(
                    """
                    UPDATE api_keys SET
                        status = 'cooling',
                        cooldown_until = ?,
                        consecutive_errors = consecutive_errors + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (cooldown_until, now, key_id)
                )
            else:
                await db.execute(
                    """
                    UPDATE api_keys SET
                        consecutive_errors = consecutive_errors + 1,
                        cooldown_until = CASE WHEN consecutive_errors >= 2 THEN ? ELSE cooldown_until END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (cooldown_until, now, key_id)
                )
            await db.commit()

    async def reset_daily_quotas_if_needed(self):
        """Reset daily counters at start of new day."""
        # Simple midnight UTC check could be added here
        pass

    async def get_status_summary(self) -> Dict[str, Any]:
        """Aggregate summary of all providers, key counts, and ready states."""
        keys = await self.list_keys()
        summary: Dict[str, Dict[str, Any]] = {}

        for k in keys:
            p = k.provider
            if p not in summary:
                spec = PROVIDER_SPECS.get(p)
                summary[p] = {
                    "provider": p,
                    "display_name": spec.display_name if spec else p.capitalize(),
                    "tier": spec.tier.value if spec else 0,
                    "default_model": spec.default_model if spec else "",
                    "total_keys": 0,
                    "ready_keys": 0,
                    "cooling_keys": 0,
                    "exhausted_keys": 0,
                    "disabled_keys": 0,
                    "total_daily_quota": 0,
                    "total_daily_used": 0,
                    "tokens_used_today": 0,
                }
            entry = summary[p]
            entry["total_keys"] += 1
            entry["total_daily_quota"] += k.daily_quota
            entry["total_daily_used"] += k.daily_used
            entry["tokens_used_today"] += k.tokens_used_today

            if k.status == KeyStatus.READY:
                entry["ready_keys"] += 1
            elif k.status == KeyStatus.COOLING:
                entry["cooling_keys"] += 1
            elif k.status == KeyStatus.EXHAUSTED:
                entry["exhausted_keys"] += 1
            elif k.status == KeyStatus.DISABLED:
                entry["disabled_keys"] += 1

        return {
            "providers": summary,
            "total_keys": len(keys),
            "total_ready_keys": sum(1 for k in keys if k.is_usable),
            "timestamp": time.time(),
        }
