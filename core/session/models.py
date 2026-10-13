"""
Session & Knowledge Graph Data Models
──────────────────────────────────────
Defines data structures for multi-turn conversational sessions,
message branching (trees/DAGs for deviation and backtracking),
and knowledge graph entities and edges.
"""

import time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SessionModel(BaseModel):
    id: str
    title: str
    focus_domain: str = "general"
    research_mode: str = "deep_research"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    message_count: int = 0
    node_count: int = 0


class SessionCreateRequest(BaseModel):
    title: Optional[str] = None
    focus_domain: Optional[str] = "general"
    research_mode: Optional[str] = "deep_research"


class SessionUpdateRequest(BaseModel):
    title: Optional[str] = None
    focus_domain: Optional[str] = None
    research_mode: Optional[str] = None


class MessageModel(BaseModel):
    id: str
    session_id: str
    parent_message_id: Optional[str] = None
    role: str   # 'user' | 'assistant' | 'system'
    content: str
    reasoning_trace: Optional[str] = None
    status: str = "done"  # 'streaming' | 'done' | 'error'
    created_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphNodeModel(BaseModel):
    id: str
    session_id: str
    origin_message_id: Optional[str] = None
    node_type: str   # 'entity' | 'claim' | 'source' | 'hypothesis'
    label: str
    description: Optional[str] = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class GraphEdgeModel(BaseModel):
    id: str
    session_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str  # 'supports' | 'contradicts' | 'derived_from' | 'subtopic_of' | 'cites'
    weight: float = 1.0
    evidence_text: Optional[str] = ""
    created_at: float = Field(default_factory=time.time)


class SessionGraphModel(BaseModel):
    session_id: str
    nodes: List[GraphNodeModel] = Field(default_factory=list)
    edges: List[GraphEdgeModel] = Field(default_factory=list)


class ChatTurnRequest(BaseModel):
    message: str
    parent_message_id: Optional[str] = None   # Specify to branch / backtrack!
    turn_id: Optional[str] = None             # Optional client-generated turn ID for WebSocket streaming
    focus_domain: Optional[str] = None
    research_mode: Optional[str] = None
    llm_ratio: int = Field(70, ge=0, le=100)
    scraper_ratio: int = Field(30, ge=0, le=100)
