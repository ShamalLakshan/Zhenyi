"""
Knowledge Graph Bridge Linker & Unification Engine
──────────────────────────────────────────────────
Ensures that when new nodes are added to a session knowledge graph,
they are intelligently and sensibly linked to already existing nodes,
preventing multiple isolated subgraphs and creating a unified knowledge graph.
"""

import re
import uuid
import time
import logging
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict, deque

from core.session.models import GraphNodeModel, GraphEdgeModel

logger = logging.getLogger(__name__)

STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'and', 'or', 'of', 'in', 'for',
    'with', 'on', 'at', 'to', 'from', 'by', 'that', 'this', 'it', 'as', 'be', 'an',
    'into', 'which', 'their', 'its', 'these', 'those', 'then', 'than', 'such', 'when',
    'can', 'could', 'should', 'would', 'may', 'might', 'must', 'have', 'has', 'had'
}

CONTRAST_KEYWORDS = {
    'contrast', 'contradict', 'contradicts', 'dispute', 'disputes', 'disputed',
    'however', 'fails', 'failing', 'unlike', 'whereas', 'limitation', 'limitations',
    'flaw', 'flaws', 'versus', 'vs', 'opposing', 'disagree', 'disagrees', 'counter',
    'refute', 'refutes', 'challenge', 'challenges', 'outperform', 'outperformed'
}

CAUSAL_KEYWORDS = {
    'causes', 'leads to', 'triggers', 'results in', 'implements', 'drives', 'enables',
    'induces', 'promotes', 'activates', 'inhibits', 'suppresses'
}


class GraphBridgeLinker:
    """Discovers and constructs proper semantic edges between new and existing graph nodes."""

    @staticmethod
    def tokenize(text: str) -> Set[str]:
        """Extract meaningful normalized words and sub-tokens from text."""
        if not text:
            return set()
        clean = text.lower()
        words = re.findall(r'[a-zA-Z0-9_\-]{2,}', clean)
        tokens = set()
        for w in words:
            if w not in STOPWORDS and len(w) >= 2:
                tokens.add(w)
                # Split compound terms (e.g. crispr-cas9 -> crispr, cas9)
                subparts = re.split(r'[-_]', w)
                for sp in subparts:
                    if len(sp) >= 2 and sp not in STOPWORDS:
                        tokens.add(sp)
        return tokens

    @staticmethod
    def find_cooccurrence_sentence(text: str, label_a: str, label_b: str) -> Optional[str]:
        """Find a sentence in text where both labels (or parts of them) appear."""
        if not text:
            return None
        clean_a = re.escape(label_a[:25].strip())
        clean_b = re.escape(label_b[:25].strip())
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for s in sentences:
            if re.search(clean_a, s, re.IGNORECASE) and re.search(clean_b, s, re.IGNORECASE):
                return s.strip()[:200]
        return None

    @classmethod
    def score_node_pair(
        cls,
        node_a: GraphNodeModel,
        node_b: GraphNodeModel,
        context_text: str = ""
    ) -> Tuple[float, str, str]:
        """
        Calculates semantic affinity, optimal relationship type, and evidence quote
        between two nodes (typically one new node and one existing node).
        Returns: (score, relation_type, evidence_text)
        """
        tokens_label_a = cls.tokenize(node_a.label)
        tokens_label_b = cls.tokenize(node_b.label)
        tokens_full_a = tokens_label_a | cls.tokenize(node_a.description or "")
        tokens_full_b = tokens_label_b | cls.tokenize(node_b.description or "")

        score = 0.0

        # 1. Label Token Jaccard Overlap
        label_union = tokens_label_a | tokens_label_b
        if label_union:
            label_jaccard = len(tokens_label_a & tokens_label_b) / len(label_union)
            score += label_jaccard * 0.55

        # 2. Substring & Acronym Containment
        norm_a = node_a.label.strip().lower()
        norm_b = node_b.label.strip().lower()
        if len(norm_a) >= 4 and len(norm_b) >= 4:
            if norm_a in norm_b or norm_b in norm_a:
                score += 0.35

        # 3. Description Token Overlap
        full_union = tokens_full_a | tokens_full_b
        if full_union:
            desc_overlap = len(tokens_full_a & tokens_full_b) / max(1, min(len(tokens_full_a), len(tokens_full_b)))
            score += min(0.3, desc_overlap * 0.3)

        # 4. Co-occurrence in answer / research context
        cooc_quote = cls.find_cooccurrence_sentence(context_text, node_a.label, node_b.label)
        if cooc_quote:
            score += 0.35

        # Determine relation type
        desc_combined = (node_a.description or "") + " " + (node_b.description or "")
        desc_tokens = cls.tokenize(desc_combined)
        has_contrast = bool(desc_tokens & CONTRAST_KEYWORDS)

        # Relation typing heuristics
        if has_contrast and (node_a.node_type == "claim" or node_b.node_type == "claim"):
            relation = "contradicts"
            evidence = cooc_quote or f"Conflicting findings identified between '{node_a.label}' and '{node_b.label}'."
        elif node_a.node_type == "claim" and node_b.node_type == "claim":
            relation = "supports"
            evidence = cooc_quote or f"Corroborating claim asserting mechanisms related to '{node_b.label}'."
        elif node_a.node_type == "claim" and node_b.node_type == "entity":
            relation = "supports"
            evidence = cooc_quote or f"Empirical claim characterizing core mechanism of '{node_b.label}'."
        elif node_a.node_type == "entity" and node_b.node_type == "claim":
            relation = "supports"
            evidence = cooc_quote or f"Entity underlying empirical observation in '{node_b.label}'."
        elif node_a.node_type == "entity" and node_b.node_type == "entity":
            if (norm_a in norm_b or norm_b in norm_a) or score > 0.4:
                relation = "subtopic"
                evidence = cooc_quote or f"Direct structural subtopic and lineage connection to '{node_b.label}'."
            else:
                relation = "relates_to"
                evidence = cooc_quote or f"Thematic association established with '{node_b.label}'."
        elif node_a.node_type == "source" or node_b.node_type == "source":
            relation = "cited_by"
            evidence = cooc_quote or f"Citations supporting technical assertion on '{node_b.label}'."
        elif node_a.node_type == "hypothesis" or node_b.node_type == "hypothesis":
            relation = "alternative_to" if has_contrast else "supports"
            evidence = cooc_quote or f"Hypothesis framing for '{node_b.label}'."
        else:
            relation = "relates_to"
            evidence = cooc_quote or f"Cross-inquiry relation linking '{node_a.label}' to '{node_b.label}'."

        return score, relation, evidence

    @classmethod
    def bridge_new_nodes_to_existing(
        cls,
        session_id: str,
        existing_nodes: List[GraphNodeModel],
        existing_edges: List[GraphEdgeModel],
        new_nodes: List[GraphNodeModel],
        new_edges: List[GraphEdgeModel],
        query: str = "",
        answer: str = "",
    ) -> List[GraphEdgeModel]:
        """
        Examines existing nodes and new nodes, builds an undirected connectivity model,
        and constructs proper sensible links connecting all new components into the
        existing knowledge graph.
        """
        if not existing_nodes or not new_nodes:
            return []

        now = time.time()
        context_text = f"{query}\n\n{answer}"
        existing_id_set = {n.id for n in existing_nodes}
        new_id_set = {n.id for n in new_nodes}

        # Combine all edges to determine current connectivity
        all_edges = list(existing_edges) + list(new_edges)
        adj: Dict[str, Set[str]] = defaultdict(set)
        for e in all_edges:
            adj[e.source_node_id].add(e.target_node_id)
            adj[e.target_node_id].add(e.source_node_id)

        # Find connected components containing existing nodes
        existing_connected_component: Set[str] = set()
        queue = deque(list(existing_id_set))
        visited: Set[str] = set(existing_id_set)

        while queue:
            curr = queue.popleft()
            existing_connected_component.add(curr)
            for neighbor in adj.get(curr, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        # Identify newly added nodes that are not yet connected to the existing graph
        unconnected_new_nodes = [n for n in new_nodes if n.id not in existing_connected_component]

        bridge_edges: List[GraphEdgeModel] = []
        created_pairs: Set[Tuple[str, str]] = set()

        for e in all_edges:
            created_pairs.add((e.source_node_id, e.target_node_id))
            created_pairs.add((e.target_node_id, e.source_node_id))

        # Partition unconnected new nodes into internal connected components
        unconnected_ids = {n.id for n in unconnected_new_nodes}
        new_node_map = {n.id: n for n in new_nodes}
        components: List[List[GraphNodeModel]] = []
        comp_visited: Set[str] = set()

        for n_id in unconnected_ids:
            if n_id not in comp_visited:
                comp = []
                c_q = deque([n_id])
                comp_visited.add(n_id)
                while c_q:
                    curr = c_q.popleft()
                    if curr in new_node_map:
                        comp.append(new_node_map[curr])
                    for nbr in adj.get(curr, set()):
                        if nbr in unconnected_ids and nbr not in comp_visited:
                            comp_visited.add(nbr)
                            c_q.append(nbr)
                components.append(comp)

        # Find a primary anchor node in the existing graph
        # Prefer existing entity nodes or nodes with highest degree
        deg_map: Dict[str, int] = defaultdict(int)
        for e in existing_edges:
            deg_map[e.source_node_id] += 1
            deg_map[e.target_node_id] += 1

        existing_entities = [n for n in existing_nodes if n.node_type == "entity"]
        root_existing = max(
            existing_entities or existing_nodes,
            key=lambda n: deg_map.get(n.id, 0),
            default=existing_nodes[0]
        )

        # 1. For each disconnected component, establish at least one solid bridge to existing graph
        for comp in components:
            best_score = -1.0
            best_new_node: Optional[GraphNodeModel] = None
            best_exist_node: Optional[GraphNodeModel] = None
            best_rel = "relates_to"
            best_ev = ""

            for n_node in comp:
                for e_node in existing_nodes:
                    s, rel, ev = cls.score_node_pair(n_node, e_node, context_text)
                    if s > best_score:
                        best_score = s
                        best_new_node = n_node
                        best_exist_node = e_node
                        best_rel = rel
                        best_ev = ev

            # If semantic scoring found a link or we fallback to root existing anchor
            if best_new_node and best_exist_node and best_score >= 0.12:
                target_new = best_new_node
                target_exist = best_exist_node
                final_rel = best_rel
                final_ev = best_ev
            else:
                # Fallback: connect the most prominent node of the new component to the root existing node
                target_new = next((n for n in comp if n.node_type == "entity"), comp[0])
                target_exist = root_existing
                final_rel = "subtopic" if target_new.node_type == "entity" else "relates_to"
                final_ev = f"Investigation inquiry trajectory connects '{target_new.label}' to '{target_exist.label}'."

            edge_key = (target_new.id, target_exist.id)
            if edge_key not in created_pairs:
                bridge_e = GraphEdgeModel(
                    id=f"edge_bridge_{uuid.uuid4().hex[:10]}",
                    session_id=session_id,
                    source_node_id=target_new.id,
                    target_node_id=target_exist.id,
                    relation_type=final_rel,
                    weight=0.9,
                    evidence_text=final_ev,
                    created_at=now
                )
                bridge_edges.append(bridge_e)
                created_pairs.add(edge_key)
                created_pairs.add((target_exist.id, target_new.id))

                # Also mark all nodes in this component as connected
                for n_node in comp:
                    existing_connected_component.add(n_node.id)

        # 2. Check for high-affinity cross-links (e.g. claims that support or contradict existing claims)
        # Even if already indirectly connected, direct domain edges between specific nodes make the graph rich!
        for n_node in new_nodes:
            for e_node in existing_nodes:
                pair = (n_node.id, e_node.id)
                if pair in created_pairs:
                    continue
                score, rel, ev = cls.score_node_pair(n_node, e_node, context_text)
                # Strong threshold for auxiliary cross-links (e.g. contradictions or high semantic overlap)
                if score >= 0.45 or (rel == "contradicts" and score >= 0.35):
                    aux_e = GraphEdgeModel(
                        id=f"edge_bridge_{uuid.uuid4().hex[:10]}",
                        session_id=session_id,
                        source_node_id=n_node.id,
                        target_node_id=e_node.id,
                        relation_type=rel,
                        weight=0.95,
                        evidence_text=ev,
                        created_at=now
                    )
                    bridge_edges.append(aux_e)
                    created_pairs.add(pair)
                    created_pairs.add((e_node.id, n_node.id))

        if bridge_edges:
            logger.info(
                f"[GraphBridgeLinker] Successfully generated {len(bridge_edges)} bridging edges "
                f"unifying {len(new_nodes)} new nodes with {len(existing_nodes)} existing nodes."
            )

        return bridge_edges

    @classmethod
    def reconcile_graph(
        cls,
        session_id: str,
        nodes: List[GraphNodeModel],
        edges: List[GraphEdgeModel],
        context_hint: str = ""
    ) -> List[GraphEdgeModel]:
        """
        Analyzes an entire knowledge graph for isolated nodes or disconnected components
        and synthesizes sensible edges so the graph forms a single connected whole.
        """
        if len(nodes) < 2:
            return []

        now = time.time()
        adj: Dict[str, Set[str]] = defaultdict(set)
        created_pairs: Set[Tuple[str, str]] = set()

        for e in edges:
            adj[e.source_node_id].add(e.target_node_id)
            adj[e.target_node_id].add(e.source_node_id)
            created_pairs.add((e.source_node_id, e.target_node_id))
            created_pairs.add((e.target_node_id, e.source_node_id))

        # Compute connected components
        visited: Set[str] = set()
        components: List[List[GraphNodeModel]] = []
        node_map = {n.id: n for n in nodes}

        for n in nodes:
            if n.id not in visited:
                comp = []
                q = deque([n.id])
                visited.add(n.id)
                while q:
                    curr = q.popleft()
                    if curr in node_map:
                        comp.append(node_map[curr])
                    for nbr in adj.get(curr, set()):
                        if nbr not in visited and nbr in node_map:
                            visited.add(nbr)
                            q.append(nbr)
                components.append(comp)

        # If already a single connected component, nothing to do
        if len(components) <= 1:
            return []

        # Sort components by size descending (component 0 is primary)
        components.sort(key=len, reverse=True)
        primary_comp = components[0]
        reconciled_edges: List[GraphEdgeModel] = []

        # Connect each satellite component to primary component
        for sat_comp in components[1:]:
            best_score = -1.0
            best_sat_node: Optional[GraphNodeModel] = None
            best_prim_node: Optional[GraphNodeModel] = None
            best_rel = "relates_to"
            best_ev = ""

            for sat_n in sat_comp:
                for prim_n in primary_comp:
                    s, rel, ev = cls.score_node_pair(sat_n, prim_n, context_hint)
                    if s > best_score:
                        best_score = s
                        best_sat_node = sat_n
                        best_prim_node = prim_n
                        best_rel = rel
                        best_ev = ev

            if not best_sat_node or not best_prim_node or best_score < 0.1:
                # Pick the most prominent node of satellite and primary
                best_sat_node = next((n for n in sat_comp if n.node_type == "entity"), sat_comp[0])
                best_prim_node = next((n for n in primary_comp if n.node_type == "entity"), primary_comp[0])
                best_rel = "subtopic" if best_sat_node.node_type == "entity" else "relates_to"
                best_ev = f"Cross-investigation link connecting '{best_sat_node.label}' to '{best_prim_node.label}'."

            edge_key = (best_sat_node.id, best_prim_node.id)
            if edge_key not in created_pairs:
                reconciled_e = GraphEdgeModel(
                    id=f"edge_reconciled_{uuid.uuid4().hex[:10]}",
                    session_id=session_id,
                    source_node_id=best_sat_node.id,
                    target_node_id=best_prim_node.id,
                    relation_type=best_rel,
                    weight=0.85,
                    evidence_text=best_ev,
                    created_at=now
                )
                reconciled_edges.append(reconciled_e)
                created_pairs.add(edge_key)
                created_pairs.add((best_prim_node.id, best_sat_node.id))

                # Satellite component is now part of primary component
                primary_comp.extend(sat_comp)

        return reconciled_edges
