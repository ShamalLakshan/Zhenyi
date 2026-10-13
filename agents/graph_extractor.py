"""
Knowledge Graph Extraction Agent
─────────────────────────────────
Extracts structured entity nodes, verifiable claims, citations, and relational
edges (supports, contradicts, implements, alternative_to) from research findings.
Utilizes ultra-fast Tier 0 inference (Cerebras/Groq) with deterministic fallback.
"""

import json
import logging
import time
from typing import Tuple, List, Optional
from core.session.models import GraphNodeModel, GraphEdgeModel
from core.session.triple_extractor import KnowledgeTripleExtractor
from core.session.graph_linker import GraphBridgeLinker
from core.gateway.gateway import LLMGateway
from core.key_pool import KeyPool

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a rigorous Knowledge Graph Knowledge Engineer for deep scientific and technical research.
Your task is to extract structured entities, empirical claims, and relationships from research findings into a directed knowledge graph.

CRITICAL INSTRUCTIONS:
1. Extract distinct, specific nodes. Node types MUST be one of:
   - "entity": Specific algorithm, software, protein, material, organization, law, or concept.
   - "claim": Concrete verifiable assertion or quantified finding (e.g. "SpCas9-HF1 reduces off-target cleavage by 90%").
   - "source": Primary publication, paper, URL, or author cited.
   - "hypothesis": An open question or inferred thesis.
2. Extract directed edges connecting nodes. Relation types MUST be one of:
   - "supports": Evidence supports an entity, claim, or hypothesis.
   - "contradicts": Evidence disputes or contradicts another claim.
   - "implements": System or method implements a theory or algorithm.
   - "alternative_to": Competing paradigm or rival approach.
   - "cited_by": Source document or authority cited by an assertion.
   - "subtopic": Sub-domain or component of a parent entity.
3. Every edge must include a short evidence quote (1-2 sentences).
4. Strictly avoid vague concepts. Avoid AI boilerplate.
5. CROSS-GRAPH LINKING & UNIFICATION:
   When existing nodes from earlier turns of the investigation are provided:
   - You MUST generate edges that connect newly extracted nodes to relevant existing nodes.
   - Use the exact ID of the existing node in edge "source" or "target".
   - If a new finding refers directly to an established entity or concept, reuse its existing ID instead of creating a duplicate node.
   - Ensure the new discoveries integrate into the overall knowledge graph rather than forming isolated clusters.

OUTPUT FORMAT: Return ONLY a valid JSON object with keys "nodes" and "edges":
{
  "nodes": [
    {
      "id": "e1",
      "type": "entity",
      "label": "SpCas9-HF1",
      "description": "High-fidelity engineered Cas9 endonuclease variant",
      "confidence": 0.95
    },
    {
      "id": "c1",
      "type": "claim",
      "label": "Eliminates genome-wide off-target cleavage",
      "description": "Renders off-target activity undetectable by standard sequencing methods",
      "confidence": 0.90
    }
  ],
  "edges": [
    {
      "source": "e1",
      "target": "c1",
      "relation": "supports",
      "weight": 0.95,
      "evidence": "SpCas9-HF1 engineered variant eliminated non-target double strand breaks."
    }
  ]
}
"""


class GraphExtractorAgent:
    """Agent that extracts structured knowledge graphs from analyst findings and syntheses."""

    def __init__(self, gateway_or_pool=None):
        self.gateway = gateway_or_pool if isinstance(gateway_or_pool, LLMGateway) else None
        self.pool = gateway_or_pool if isinstance(gateway_or_pool, KeyPool) else None

    async def extract_graph(
        self,
        session_id: str,
        message_id: str,
        query: str,
        answer: str,
        findings: Optional[List[str]] = None,
        sources: Optional[List[dict]] = None,
        query_id: str = "",
        existing_nodes: Optional[List[GraphNodeModel]] = None,
        existing_edges: Optional[List[GraphEdgeModel]] = None,
    ) -> Tuple[List[GraphNodeModel], List[GraphEdgeModel]]:
        """
        Extract knowledge graph triples using fast LLM completion with fallback,
        ensuring sensible cross-links are established with existing graph nodes.
        Returns typed GraphNodeModel and GraphEdgeModel lists.
        """
        findings_text = "\n- ".join(findings[:12]) if findings else ""
        user_prompt = f"USER QUERY: {query}\n\n"
        if findings_text:
            user_prompt += f"ANALYST FINDINGS:\n- {findings_text}\n\n"
        user_prompt += f"SYNTHESIZED REPORT:\n{answer[:4000]}\n\n"
        if sources:
            urls = [s.get("url") or s.get("title") for s in sources if isinstance(s, dict)][:6]
            user_prompt += f"PRIMARY SOURCES: {', '.join(filter(None, urls))}\n\n"

        # Inject existing graph context to guide LLM cross-linking
        if existing_nodes:
            existing_summary = []
            for en in existing_nodes[:25]:
                existing_summary.append(
                    f'- [{en.node_type.upper()}] id="{en.id}": "{en.label}" - {en.description[:100]}'
                )
            user_prompt += (
                "ESTABLISHED KNOWLEDGE GRAPH (already in investigation):\n"
                + "\n".join(existing_summary)
                + "\n\n"
                "CRITICAL INSTRUCTION: In your JSON 'edges', connect your newly extracted nodes "
                "to relevant established nodes above using their exact 'id'. Ensure the new knowledge "
                "links into the established graph rather than forming isolated subgraphs.\n\n"
            )

        user_prompt += "Extract the core knowledge graph in JSON format as specified."

        extracted_nodes: List[GraphNodeModel] = []
        extracted_edges: List[GraphEdgeModel] = []

        # 1. Try Fast LLM extraction via Gateway or Pool
        try:
            raw_response = await self._call_fast_llm(user_prompt)
            if raw_response:
                nodes, edges = KnowledgeTripleExtractor.parse_llm_json(
                    raw_response,
                    session_id=session_id,
                    message_id=message_id,
                    existing_nodes=existing_nodes,
                )
                if len(nodes) >= 1 or len(edges) >= 1:
                    logger.info(f"[{query_id}] LLM Graph Extractor produced {len(nodes)} new nodes, {len(edges)} edges")
                    extracted_nodes = nodes
                    extracted_edges = edges
        except Exception as e:
            logger.debug(f"[{query_id}] LLM Graph extraction call failed: {e}")

        # 2. Deterministic Fallback Extraction if LLM produced empty output
        if not extracted_nodes and not extracted_edges:
            logger.info(f"[{query_id}] Utilizing deterministic fallback graph extraction")
            extracted_nodes, extracted_edges = KnowledgeTripleExtractor.extract_from_text_fallback(
                session_id=session_id,
                message_id=message_id,
                query=query,
                answer=answer,
                sources=sources or [],
                existing_nodes=existing_nodes,
            )

        # 3. Apply Semantic Bridge Linker to guarantee zero isolated components
        if existing_nodes and extracted_nodes:
            bridge_edges = GraphBridgeLinker.bridge_new_nodes_to_existing(
                session_id=session_id,
                existing_nodes=existing_nodes,
                existing_edges=existing_edges or [],
                new_nodes=extracted_nodes,
                new_edges=extracted_edges,
                query=query,
                answer=answer,
            )
            if bridge_edges:
                logger.info(f"[{query_id}] Bridge Linker added {len(bridge_edges)} links connecting to existing graph")
                extracted_edges.extend(bridge_edges)

        return extracted_nodes, extracted_edges

    async def _call_fast_llm(self, prompt: str) -> Optional[str]:
        """Calls fast Tier 0 model (Cerebras / Groq) for rapid triple generation."""
        # Check LLMGateway first
        if self.gateway is None:
            try:
                self.gateway = await LLMGateway.get_instance()
            except Exception:
                pass

        if self.gateway:
            try:
                res = await self.gateway.complete(
                    prompt=prompt,
                    system=EXTRACTION_SYSTEM_PROMPT,
                    temperature=0.1,
                    max_tokens=1500,
                )
                return res.text
            except Exception as e:
                logger.debug(f"[GraphExtractorAgent] Gateway call error: {e}")

        # Fallback to KeyPool if gateway unavailable
        if self.pool:
            try:
                from agents.analyst import AnalystAgent
                analyst = AnalystAgent("graph_extractor", self.pool, provider="groq", model="llama-3.3-70b-versatile")
                return await analyst.call(f"{EXTRACTION_SYSTEM_PROMPT}\n\n{prompt}")
            except Exception as e:
                logger.debug(f"[GraphExtractorAgent] KeyPool call error: {e}")

        return None
