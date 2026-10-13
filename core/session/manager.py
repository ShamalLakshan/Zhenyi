"""
Session & Knowledge Graph State Manager
────────────────────────────────────────
Manages SQLite tables for multi-turn conversational sessions,
message branching (decision trees / DAGs for deviation and backtracking),
and living knowledge graph nodes and edges.
"""

import aiosqlite
import json
import logging
import os
import re
import time
import uuid
from typing import Optional, List, Dict, Any, Tuple

from core.session.models import (
    SessionModel, MessageModel, GraphNodeModel, GraphEdgeModel, SessionGraphModel
)

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "zhenyi.db")


class SessionManager:
    """Manages conversational sessions, message tree lineages, and knowledge graphs."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def init_session_tables(self):
        """Create sessions, messages, and graph tables if not exists."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id              TEXT PRIMARY KEY,
                    title           TEXT NOT NULL,
                    focus_domain    TEXT DEFAULT 'general',
                    research_mode   TEXT DEFAULT 'deep_research',
                    created_at      REAL NOT NULL,
                    updated_at      REAL NOT NULL
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id                  TEXT PRIMARY KEY,
                    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    parent_message_id   TEXT REFERENCES messages(id),
                    role                TEXT NOT NULL,
                    content             TEXT NOT NULL,
                    reasoning_trace     TEXT,
                    status              TEXT DEFAULT 'done',
                    metadata_json       TEXT,
                    created_at          REAL NOT NULL
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_message_id);")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id                  TEXT PRIMARY KEY,
                    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    origin_message_id   TEXT REFERENCES messages(id),
                    node_type           TEXT NOT NULL,
                    label               TEXT NOT NULL,
                    description         TEXT,
                    confidence          REAL DEFAULT 1.0,
                    metadata_json       TEXT,
                    created_at          REAL NOT NULL
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_graph_nodes_session ON graph_nodes(session_id);")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id                  TEXT PRIMARY KEY,
                    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    source_node_id      TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                    target_node_id      TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                    relation_type       TEXT NOT NULL,
                    weight              REAL DEFAULT 1.0,
                    evidence_text       TEXT,
                    created_at          REAL NOT NULL
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_session ON graph_edges(session_id);")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS research_chunks (
                    id              TEXT PRIMARY KEY,
                    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    message_id      TEXT REFERENCES messages(id),
                    source_name     TEXT NOT NULL,
                    url             TEXT,
                    title           TEXT,
                    content_clean   TEXT NOT NULL,
                    relevance_score REAL DEFAULT 0,
                    created_at      REAL NOT NULL
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_research_chunks_session ON research_chunks(session_id);")

            # FTS5 Virtual Table for local full-text search across research chunks
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS research_chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    session_id UNINDEXED,
                    title,
                    content_clean,
                    source_name
                );
            """)

            await db.commit()
            logger.info("Session and Knowledge Graph database tables initialized")

    # ─── Session Management ───────────────────────────────────────────────────

    async def create_session(
        self,
        title: Optional[str] = None,
        focus_domain: str = "general",
        research_mode: str = "deep_research"
    ) -> SessionModel:
        """Create a new research session / chat thread."""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = time.time()
        session_title = title or "New Investigation"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (id, title, focus_domain, research_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, session_title, focus_domain, research_mode, now, now)
            )
            await db.commit()

        return SessionModel(
            id=session_id,
            title=session_title,
            focus_domain=focus_domain,
            research_mode=research_mode,
            created_at=now,
            updated_at=now,
            message_count=0,
            node_count=0,
        )

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[SessionModel]:
        """List sessions with message counts, ordered by most recently updated."""
        sessions = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT s.*, 
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as msg_count,
                       (SELECT COUNT(*) FROM graph_nodes g WHERE g.session_id = s.id) as node_count
                FROM sessions s
                ORDER BY s.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            rows = await cursor.fetchall()
            for r in rows:
                sessions.append(SessionModel(
                    id=r["id"],
                    title=r["title"],
                    focus_domain=r["focus_domain"] or "general",
                    research_mode=r["research_mode"] or "deep_research",
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    message_count=r["msg_count"],
                    node_count=r["node_count"],
                ))
        return sessions

    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Get session details."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT s.*, 
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as msg_count,
                       (SELECT COUNT(*) FROM graph_nodes g WHERE g.session_id = s.id) as node_count
                FROM sessions s
                WHERE s.id = ?
                """,
                (session_id,)
            )
            r = await cursor.fetchone()
            if not r:
                return None
            return SessionModel(
                id=r["id"],
                title=r["title"],
                focus_domain=r["focus_domain"] or "general",
                research_mode=r["research_mode"] or "deep_research",
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                message_count=r["msg_count"],
                node_count=r["node_count"],
            )

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        focus_domain: Optional[str] = None,
        research_mode: Optional[str] = None
    ) -> Optional[SessionModel]:
        """Update session attributes."""
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if focus_domain is not None:
            updates.append("focus_domain = ?")
            params.append(focus_domain)
        if research_mode is not None:
            updates.append("research_mode = ?")
            params.append(research_mode)

        if not updates:
            return await self.get_session(session_id)

        updates.append("updated_at = ?")
        params.append(time.time())
        params.append(session_id)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
                params
            )
            await db.commit()

        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete session and all its messages, graphs, and chunks."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM graph_nodes WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM graph_edges WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM research_chunks WHERE session_id = ?", (session_id,))
            await db.commit()
            return True

    # ─── Message & Tree Branching Management ──────────────────────────────────

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        parent_message_id: Optional[str] = None,
        reasoning_trace: Optional[str] = None,
        status: str = "done",
        metadata: Optional[Dict[str, Any]] = None
    ) -> MessageModel:
        """Add a message node to the session's conversation tree."""
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = time.time()
        meta_json = json.dumps(metadata or {})

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO messages (
                    id, session_id, parent_message_id, role, content,
                    reasoning_trace, status, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, session_id, parent_message_id, role, content, reasoning_trace, status, meta_json, now)
            )
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id)
            )
            await db.commit()

        return MessageModel(
            id=msg_id,
            session_id=session_id,
            parent_message_id=parent_message_id,
            role=role,
            content=content,
            reasoning_trace=reasoning_trace,
            status=status,
            created_at=now,
            metadata=metadata or {},
        )

    async def get_messages(
        self,
        session_id: str,
        branch_leaf_id: Optional[str] = None
    ) -> List[MessageModel]:
        """
        Get messages for a session.
        If branch_leaf_id is supplied, traverses up parent_message_id to reconstruct
        the exact active branch lineage (backtracking/deviation support!).
        Otherwise returns all messages in chronological order.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if branch_leaf_id:
                # Traverse tree upwards from leaf to root
                lineage = []
                curr_id = branch_leaf_id
                while curr_id:
                    cursor = await db.execute("SELECT * FROM messages WHERE id = ?", (curr_id,))
                    row = await cursor.fetchone()
                    if not row:
                        break
                    lineage.append(row)
                    curr_id = row["parent_message_id"]

                # Reverse so root is first
                lineage.reverse()
                rows = lineage
            else:
                cursor = await db.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                    (session_id,)
                )
                rows = await cursor.fetchall()

            messages = []
            for r in rows:
                meta = {}
                if r["metadata_json"]:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        pass

                messages.append(MessageModel(
                    id=r["id"],
                    session_id=r["session_id"],
                    parent_message_id=r["parent_message_id"],
                    role=r["role"],
                    content=r["content"],
                    reasoning_trace=r["reasoning_trace"],
                    status=r["status"],
                    created_at=r["created_at"],
                    metadata=meta,
                ))
            return messages

    # ─── Knowledge Graph Elements ─────────────────────────────────────────────

    async def add_graph_elements(
        self,
        session_id: str,
        nodes: List[GraphNodeModel],
        edges: List[GraphEdgeModel]
    ):
        """Insert knowledge graph nodes and edges into the session graph."""
        if not nodes and not edges:
            return

        async with aiosqlite.connect(self.db_path) as db:
            for n in nodes:
                meta_json = json.dumps(n.metadata or {})
                await db.execute(
                    """
                    INSERT OR REPLACE INTO graph_nodes (
                        id, session_id, origin_message_id, node_type, label,
                        description, confidence, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (n.id, session_id, n.origin_message_id, n.node_type, n.label,
                     n.description, n.confidence, meta_json, n.created_at)
                )

            for e in edges:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO graph_edges (
                        id, session_id, source_node_id, target_node_id,
                        relation_type, weight, evidence_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (e.id, session_id, e.source_node_id, e.target_node_id,
                     e.relation_type, e.weight, e.evidence_text, e.created_at)
                )
            await db.commit()

    async def get_session_graph(self, session_id: str) -> SessionGraphModel:
        """Retrieve cumulative Knowledge Graph for a session."""
        nodes: List[GraphNodeModel] = []
        edges: List[GraphEdgeModel] = []

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute("SELECT * FROM graph_nodes WHERE session_id = ?", (session_id,))
            for r in await cursor.fetchall():
                meta = {}
                if r["metadata_json"]:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        pass
                nodes.append(GraphNodeModel(
                    id=r["id"],
                    session_id=r["session_id"],
                    origin_message_id=r["origin_message_id"],
                    node_type=r["node_type"],
                    label=r["label"],
                    description=r["description"] or "",
                    confidence=r["confidence"] or 1.0,
                    metadata=meta,
                    created_at=r["created_at"],
                ))

            cursor = await db.execute("SELECT * FROM graph_edges WHERE session_id = ?", (session_id,))
            for r in await cursor.fetchall():
                edges.append(GraphEdgeModel(
                    id=r["id"],
                    session_id=r["session_id"],
                    source_node_id=r["source_node_id"],
                    target_node_id=r["target_node_id"],
                    relation_type=r["relation_type"],
                    weight=r["weight"] or 1.0,
                    evidence_text=r["evidence_text"] or "",
                    created_at=r["created_at"],
                ))

        return SessionGraphModel(session_id=session_id, nodes=nodes, edges=edges)

    async def reconcile_session_graph(self, session_id: str) -> SessionGraphModel:
        """
        Runs graph reconciliation over the cumulative session graph,
        identifying any disconnected components and inserting bridging edges
        so the knowledge graph is unified.
        """
        from core.session.graph_linker import GraphBridgeLinker
        curr_graph = await self.get_session_graph(session_id)
        if len(curr_graph.nodes) < 2:
            return curr_graph

        reconciled_edges = GraphBridgeLinker.reconcile_graph(
            session_id=session_id,
            nodes=curr_graph.nodes,
            edges=curr_graph.edges,
        )
        if reconciled_edges:
            logger.info(f"Reconciled {len(reconciled_edges)} edges to unify session knowledge graph")
            await self.add_graph_elements(session_id, [], reconciled_edges)
            return await self.get_session_graph(session_id)

        return curr_graph

    async def build_conversation_context(
        self,
        session_id: str,
        current_query: str,
        parent_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Assemble multi-turn conversational context and established graph entities
        to ground the orchestrator and analyst agents on follow-up questions.
        """
        # 1. Retrieve prior turns along active branch
        prior_messages = await self.get_messages(session_id, branch_leaf_id=parent_message_id)

        # 2. Retrieve established knowledge graph entities
        graph = await self.get_session_graph(session_id)
        established_entities = [
            {"label": n.label, "type": n.node_type, "desc": n.description}
            for n in graph.nodes[:15]
        ]

        turns_summary = []
        for m in prior_messages[-6:]:  # Keep last 3 exchanges (6 messages)
            turns_summary.append({
                "role": m.role,
                "content": m.content[:400]
            })

        # 3. Search prior research chunks for semantic continuity
        prior_chunks = await self.search_research_chunks(session_id, current_query, limit=3)
        relevant_prior = [
            {"source": c["source"], "title": c["title"], "content": c["content"][:300]}
            for c in prior_chunks
        ]

        return {
            "is_follow_up": len(prior_messages) > 0,
            "turns_history": turns_summary,
            "established_entities": established_entities,
            "relevant_prior_chunks": relevant_prior,
            "total_prior_turns": len(prior_messages),
        }

    # ─── Research Chunks & Full-Text Provenance ─────────────────────────────────

    async def add_research_chunks(
        self,
        session_id: str,
        message_id: str,
        chunks: List[dict]
    ):
        """Insert scraped and synthesized research chunks into database and FTS5 index."""
        if not chunks:
            return

        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            for c in chunks:
                chunk_id = f"chk_{uuid.uuid4().hex[:10]}"
                title = str(c.get("title", ""))[:200]
                content = str(c.get("content", ""))
                source = str(c.get("source", "web"))
                url = str(c.get("url", ""))
                score = float(c.get("score", 0.0) or 0.0)

                await db.execute(
                    """
                    INSERT INTO research_chunks (
                        id, session_id, message_id, source_name, url, title,
                        content_clean, relevance_score, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (chunk_id, session_id, message_id, source, url, title, content, score, now)
                )

                try:
                    await db.execute(
                        """
                        INSERT INTO research_chunks_fts (chunk_id, session_id, title, content_clean, source_name)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (chunk_id, session_id, title, content, source)
                    )
                except Exception as fts_err:
                    logger.debug(f"[SessionManager] FTS insert note: {fts_err}")

            await db.commit()

    async def search_research_chunks(
        self,
        session_id: str,
        query: str,
        limit: int = 5
    ) -> List[dict]:
        """Search previously retrieved research chunks in the session using SQLite FTS5."""
        clean_q = re.sub(r"[^\w\s]", " ", query).strip()
        terms = [t for t in clean_q.split() if len(t) > 2][:5]
        if not terms:
            return []
        match_expr = " OR ".join(terms)

        results = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                cursor = await db.execute(
                    """
                    SELECT c.id, c.source_name, c.title, c.url, c.content_clean, c.relevance_score
                    FROM research_chunks_fts f
                    JOIN research_chunks c ON f.chunk_id = c.id
                    WHERE f.session_id = ? AND research_chunks_fts MATCH ?
                    LIMIT ?
                    """,
                    (session_id, match_expr, limit)
                )
                rows = await cursor.fetchall()
                for r in rows:
                    results.append({
                        "id": r["id"],
                        "source": r["source_name"],
                        "title": r["title"],
                        "url": r["url"],
                        "content": r["content_clean"],
                        "score": r["relevance_score"],
                    })
            except Exception as e:
                logger.debug(f"[SessionManager] FTS search note: {e}")

        return results

    async def get_session_contradictions(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve all identified contradictions and disputed claim pairs for a session."""
        contradictions = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT 
                    e.id as edge_id, e.relation_type, e.weight, e.evidence_text, e.created_at,
                    s.id as source_id, s.label as source_label, s.description as source_desc, s.node_type as source_type,
                    t.id as target_id, t.label as target_label, t.description as target_desc, t.node_type as target_type
                FROM graph_edges e
                JOIN graph_nodes s ON e.source_node_id = s.id
                JOIN graph_nodes t ON e.target_node_id = t.id
                WHERE e.session_id = ? AND e.relation_type = 'contradicts'
                ORDER BY e.created_at DESC
                """,
                (session_id,)
            )
            rows = await cursor.fetchall()
            for r in rows:
                contradictions.append({
                    "edge_id": r["edge_id"],
                    "evidence_text": r["evidence_text"],
                    "weight": r["weight"],
                    "source_node": {
                        "id": r["source_id"],
                        "label": r["source_label"],
                        "description": r["source_desc"],
                        "type": r["source_type"],
                    },
                    "target_node": {
                        "id": r["target_id"],
                        "label": r["target_label"],
                        "description": r["target_desc"],
                        "type": r["target_type"],
                    },
                    "created_at": r["created_at"],
                })
        return contradictions
