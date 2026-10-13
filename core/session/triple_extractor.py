"""
Knowledge Graph Triple Extractor
─────────────────────────────────
Extracts structured entities, claims, sources, and relationships (nodes & edges)
from research analysis and synthesized answers.
"""

import json
import logging
import re
import uuid
import time
from typing import List, Dict, Any, Tuple, Optional

from core.session.models import GraphNodeModel, GraphEdgeModel

logger = logging.getLogger(__name__)


class KnowledgeTripleExtractor:
    """Extracts typed Knowledge Graph nodes and edges from research texts."""

    @staticmethod
    def extract_from_text_fallback(
        session_id: str,
        message_id: str,
        query: str,
        answer: str,
        sources: Optional[List[str]] = None,
        existing_nodes: Optional[List[GraphNodeModel]] = None,
    ) -> Tuple[List[GraphNodeModel], List[GraphEdgeModel]]:
        """
        Deterministic, fast fallback extractor when LLM extraction is unavailable.
        Builds a central topic node, key bullet claims, and source nodes,
        linking to existing nodes when available.
        """
        nodes: List[GraphNodeModel] = []
        edges: List[GraphEdgeModel] = []
        now = time.time()

        # 1. Central Topic Node
        topic_slug = re.sub(r'[^a-zA-Z0-9]', '_', query[:30]).strip('_').lower()
        topic_id = f"node_topic_{topic_slug}_{uuid.uuid4().hex[:6]}"
        nodes.append(GraphNodeModel(
            id=topic_id,
            session_id=session_id,
            origin_message_id=message_id,
            node_type="entity",
            label=query[:45].strip(),
            description=f"Primary research topic: {query}",
            confidence=1.0,
            created_at=now
        ))

        # Cross-link new topic node to established root node if available
        if existing_nodes:
            existing_anchor = next(
                (n for n in existing_nodes if n.node_type == "entity"),
                existing_nodes[0]
            )
            edges.append(GraphEdgeModel(
                id=f"edge_cross_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                source_node_id=topic_id,
                target_node_id=existing_anchor.id,
                relation_type="subtopic",
                weight=0.9,
                evidence_text=f"Sub-inquiry trajectory for topic: {query}",
                created_at=now
            ))

        # 2. Extract Claim Nodes from Key Sentences / Paragraphs
        paragraphs = [p.strip() for p in answer.split("\n\n") if len(p.strip()) > 30]
        for idx, para in enumerate(paragraphs[:4]):
            first_sentence = para.split(".")[0].strip()
            if len(first_sentence) < 15:
                continue
            claim_id = f"node_claim_{idx}_{uuid.uuid4().hex[:6]}"
            nodes.append(GraphNodeModel(
                id=claim_id,
                session_id=session_id,
                origin_message_id=message_id,
                node_type="claim",
                label=first_sentence[:50] + ("..." if len(first_sentence) > 50 else ""),
                description=para[:250],
                confidence=0.85,
                created_at=now
            ))
            edges.append(GraphEdgeModel(
                id=f"edge_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                source_node_id=topic_id,
                target_node_id=claim_id,
                relation_type="supports",
                weight=1.0,
                evidence_text=first_sentence,
                created_at=now
            ))

        # 3. Source Nodes
        if sources:
            for idx, src in enumerate(sources[:3]):
                src_id = f"node_src_{idx}_{uuid.uuid4().hex[:6]}"
                if isinstance(src, dict):
                    src_url = src.get("url") or src.get("link") or ""
                    src_title = src.get("title") or src_url or f"Source {idx+1}"
                else:
                    src_url = str(src)
                    src_title = str(src)

                clean_label = src_title
                if not clean_label or clean_label.startswith("http"):
                    clean_label = src_url.replace("https://", "").replace("http://", "").split("/")[0]
                if not clean_label:
                    clean_label = f"Source {idx+1}"

                nodes.append(GraphNodeModel(
                    id=src_id,
                    session_id=session_id,
                    origin_message_id=message_id,
                    node_type="source",
                    label=clean_label[:30],
                    description=src_title[:300],
                    confidence=1.0,
                    metadata={"url": src_url, "title": src_title},
                    created_at=now
                ))
                edges.append(GraphEdgeModel(
                    id=f"edge_src_{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    source_node_id=src_id,
                    target_node_id=topic_id,
                    relation_type="cited_by",
                    weight=1.0,
                    evidence_text=src_title[:200],
                    created_at=now
                ))

        return nodes, edges

    @staticmethod
    def parse_llm_json(
        raw_json_str: str,
        session_id: str,
        message_id: str,
        existing_nodes: Optional[List[GraphNodeModel]] = None,
    ) -> Tuple[List[GraphNodeModel], List[GraphEdgeModel]]:
        """Parse structured LLM extraction output into typed models, resolving links to existing nodes."""
        nodes: List[GraphNodeModel] = []
        edges: List[GraphEdgeModel] = []
        now = time.time()

        try:
            # Strip markdown fences
            text = raw_json_str.strip()
            if "```" in text:
                parts = text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        text = part
                        break

            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                candidate = text[start:end + 1]
                data = json.loads(candidate)
            else:
                return [], []

            raw_nodes = data.get("nodes", [])
            raw_edges = data.get("edges", [])

            # Index existing nodes for deduplication and cross-linking
            existing_id_set = {n.id for n in (existing_nodes or [])}
            existing_label_map = {n.label.strip().lower(): n.id for n in (existing_nodes or [])}

            id_remap: Dict[str, str] = {}
            for en in (existing_nodes or []):
                id_remap[en.id] = en.id

            for r_node in raw_nodes:
                old_id = str(r_node.get("id") or uuid.uuid4().hex[:8])
                label = str(r_node.get("label", "Concept")).strip()
                norm_label = label.lower()

                # If concept already exists in current session graph, reuse it rather than creating a duplicate
                if old_id in existing_id_set:
                    id_remap[old_id] = old_id
                    continue
                if norm_label in existing_label_map:
                    id_remap[old_id] = existing_label_map[norm_label]
                    continue

                new_id = f"node_{uuid.uuid4().hex[:10]}"
                id_remap[old_id] = new_id

                nodes.append(GraphNodeModel(
                    id=new_id,
                    session_id=session_id,
                    origin_message_id=message_id,
                    node_type=r_node.get("type", "entity").lower(),
                    label=label[:60],
                    description=str(r_node.get("description", ""))[:300],
                    confidence=float(r_node.get("confidence", 0.9)),
                    metadata=r_node.get("metadata", {}),
                    created_at=now
                ))

            for r_edge in raw_edges:
                src_orig = str(r_edge.get("source") or "")
                tgt_orig = str(r_edge.get("target") or "")

                # Resolve mapped IDs (checking ID map, direct existing IDs, and normalized labels)
                src_mapped = (
                    id_remap.get(src_orig)
                    or (src_orig if src_orig in existing_id_set else None)
                    or existing_label_map.get(src_orig.strip().lower())
                )
                tgt_mapped = (
                    id_remap.get(tgt_orig)
                    or (tgt_orig if tgt_orig in existing_id_set else None)
                    or existing_label_map.get(tgt_orig.strip().lower())
                )

                if src_mapped and tgt_mapped and src_mapped != tgt_mapped:
                    edges.append(GraphEdgeModel(
                        id=f"edge_{uuid.uuid4().hex[:10]}",
                        session_id=session_id,
                        source_node_id=src_mapped,
                        target_node_id=tgt_mapped,
                        relation_type=r_edge.get("relation", "relates_to").lower(),
                        weight=float(r_edge.get("weight", 1.0)),
                        evidence_text=str(r_edge.get("evidence", ""))[:200],
                        created_at=now
                    ))

        except Exception as e:
            logger.debug(f"JSON graph parsing failed: {e}")

        return nodes, edges
