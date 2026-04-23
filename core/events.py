"""
Event Pub-Sub System
────────────────────
Async-safe event bus for real-time query pipeline updates.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Pipeline event types."""
    # Query lifecycle
    QUERY_STARTED = "QUERY_STARTED"
    QUERY_DONE = "QUERY_DONE"
    QUERY_ERROR = "QUERY_ERROR"
    
    # Orchestrator
    ORCHESTRATOR_STARTED = "ORCHESTRATOR_STARTED"
    ORCHESTRATOR_DONE = "ORCHESTRATOR_DONE"
    
    # Scraping
    SCRAPER_STARTED = "SCRAPER_STARTED"
    CHUNKS_COLLECTED = "CHUNKS_COLLECTED"  # Raw chunks from scraper
    SCRAPER_DONE = "SCRAPER_DONE"
    
    # Triage/Filtering
    TRIAGE_STARTED = "TRIAGE_STARTED"
    CHUNKS_SCORED = "CHUNKS_SCORED"  # Chunks with relevance scores
    CHUNKS_FILTERED = "CHUNKS_FILTERED"  # Final filtered chunks
    TRIAGE_DONE = "TRIAGE_DONE"
    
    # Analysis
    ANALYST_START = "ANALYST_START"
    ANALYST_CHUNK_SLICE = "ANALYST_CHUNK_SLICE"  # Chunks assigned to analyst
    ANALYST_FINDING = "ANALYST_FINDING"  # Individual finding from analyst
    ANALYST_DONE = "ANALYST_DONE"
    
    # Synthesis
    SYNTHESIZER_STARTED = "SYNTHESIZER_STARTED"
    SYNTHESIZER_DONE = "SYNTHESIZER_DONE"
    
    # Thought process logs
    THOUGHT_LOG = "THOUGHT_LOG"  # Generic thought chain entry


@dataclass
class PipelineEvent:
    """Immutable event emitted during query execution."""
    event_type: EventType
    query_id: str
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "query_id": self.query_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class EventBus:
    """Singleton async event bus with per-query subscriptions."""
    _instance: Optional["EventBus"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.subscriptions: dict[str, list[Callable]] = {}
        self.global_subscribers: list[Callable] = []
        self.event_history: dict[str, list[PipelineEvent]] = {}  # Store recent events

    @classmethod
    async def get_instance(cls) -> "EventBus":
        """Get or create singleton instance (thread-safe)."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def subscribe(
        self, query_id: str, callback: Callable[[PipelineEvent], None]
    ) -> None:
        """Subscribe to events for a specific query. Replays history if available."""
        try:
            if query_id not in self.subscriptions:
                self.subscriptions[query_id] = []
            self.subscriptions[query_id].append(callback)
            logger.debug(f"Subscribed to {query_id}")
            
            # Replay event history for this query
            if query_id in self.event_history:
                for event in self.event_history[query_id]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event)
                        else:
                            callback(event)
                    except Exception as e:
                        logger.debug(f"callback error during replay for {query_id}: {e}")
        except Exception as e:
            logger.error(f"subscribe error: {e}")

    async def unsubscribe(
        self, query_id: str, callback: Callable[[PipelineEvent], None]
    ) -> None:
        """Unsubscribe from events for a specific query."""
        try:
            if query_id in self.subscriptions:
                self.subscriptions[query_id] = [
                    cb for cb in self.subscriptions[query_id] if cb != callback
                ]
                if not self.subscriptions[query_id]:
                    del self.subscriptions[query_id]
            logger.debug(f"Unsubscribed from {query_id}")
        except Exception as e:
            logger.error(f"unsubscribe error: {e}")

    async def publish(self, event: PipelineEvent) -> None:
        """Publish event to all subscribers and store in history."""
        try:
            # Store in history
            if event.query_id not in self.event_history:
                self.event_history[event.query_id] = []
            self.event_history[event.query_id].append(event)
            logger.debug(f"Event stored: {event.event_type} for {event.query_id}")
            
            # Broadcast to subscribers
            await self.broadcast_to_query(event.query_id, event)
        except Exception as e:
            logger.error(f"publish error: {e}")

    async def broadcast_to_query(self, query_id: str, event: PipelineEvent) -> None:
        """Broadcast to query-specific subscribers."""
        try:
            if query_id in self.subscriptions:
                for callback in self.subscriptions[query_id]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event)
                        else:
                            callback(event)
                    except Exception as e:
                        logger.debug(f"callback error for {query_id}: {e}")
        except Exception as e:
            logger.error(f"broadcast_to_query error: {e}")

    async def clear_query_subscriptions(self, query_id: str) -> None:
        """Clean up subscriptions and history for a completed query."""
        try:
            if query_id in self.subscriptions:
                del self.subscriptions[query_id]
            if query_id in self.event_history:
                del self.event_history[query_id]
            logger.debug(f"Cleared subscriptions and history for {query_id}")
        except Exception as e:
            logger.error(f"clear_query_subscriptions error: {e}")
