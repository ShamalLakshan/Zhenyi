"""
Database Migration
──────────────────
Safe schema migration utilities for zhenyi.db.
Handles adding new columns to existing tables without data loss.
"""

import aiosqlite
import os
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


async def add_column_if_not_exists(
    db_path: str,
    table_name: str,
    column_name: str,
    column_type: str,
    default_value: str = "NULL"
) -> bool:
    """
    Add a column to a table if it doesn't already exist.
    Safe to call multiple times — no error if column exists.
    
    Returns True if column was added or already exists.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # Check if column exists
            cursor = await db.execute(f"PRAGMA table_info({table_name})")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if column_name in column_names:
                logger.debug(f"Column {table_name}.{column_name} already exists")
                return True
            
            # Add column
            sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"
            await db.execute(sql)
            await db.commit()
            logger.info(f"Added column {table_name}.{column_name} ({column_type})")
            return True
    except Exception as e:
        logger.error(f"Failed to add column {table_name}.{column_name}: {e}")
        return False


async def migrate_to_latest(db_path: str = "zhenyi.db") -> bool:
    """
    Run all pending migrations to bring database schema up to date.
    Safe to call multiple times — uses IF NOT EXISTS semantics.
    
    Returns True if migration succeeded (or was unnecessary).
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # Check if db exists and has tables
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
            )
            result = await cursor.fetchone()
            if result is None:
                logger.info("Database is empty, no migration needed")
                return True
        
        # Migration 1: Add payload columns to api_requests
        await add_column_if_not_exists(db_path, "api_requests", "tokens_in", "INTEGER", "0")
        await add_column_if_not_exists(db_path, "api_requests", "payload_json", "TEXT", "NULL")
        
        # Migration 2: Add payload column to api_responses
        await add_column_if_not_exists(db_path, "api_responses", "payload_json", "TEXT", "NULL")
        
        # Migration 3: Add payload columns to scraper_invocations
        await add_column_if_not_exists(db_path, "scraper_invocations", "raw_output_json", "TEXT", "NULL")
        await add_column_if_not_exists(db_path, "scraper_invocations", "is_compressed", "BOOLEAN", "0")
        
        # Migration 4: Add graph and hash columns to orchestrator_plan
        await add_column_if_not_exists(db_path, "orchestrator_plan", "plan_graph_json", "TEXT", "NULL")
        await add_column_if_not_exists(db_path, "orchestrator_plan", "plan_hash", "TEXT", "NULL")
        
        logger.info("Database migration completed successfully")
        return True
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        return False


async def create_query_execution_table(db_path: str = "zhenyi.db") -> bool:
    """
    Create query_execution table for real-time progress tracking.
    Safe to call multiple times — uses IF NOT EXISTS.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS query_execution (
                    query_id        TEXT PRIMARY KEY,
                    stage           TEXT,
                    status          TEXT,
                    progress_pct    REAL,
                    timing_ms       REAL,
                    error_message   TEXT,
                    updated_at      REAL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_query_execution_stage 
                ON query_execution(stage)
            """)
            await db.commit()
            logger.info("query_execution table created or already exists")
            return True
    except Exception as e:
        logger.error(f"Failed to create query_execution table: {e}")
        return False


async def init_all_tables(db_path: str = "zhenyi.db") -> bool:
    """
    Initialize database with all required tables and migrations.
    Called at application startup.
    Safe to call multiple times.
    """
    try:
        # Run migrations to update schema
        await migrate_to_latest(db_path)
        
        # Create new tables that weren't in original schema
        await create_query_execution_table(db_path)
        
        logger.info("All database tables initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False
