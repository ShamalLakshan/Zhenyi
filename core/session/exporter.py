"""
Session Export Engine
─────────────────────
Generates publication-ready exports from multi-turn research sessions:
- Markdown Research Dossiers (Executive summary, claims, citations, Mermaid diagram)
- BibTeX Reference Library (.bib) for LaTeX, Zotero, Overleaf
- Obsidian Canvas (.canvas) spatial JSON
"""

import json
import re
import time
from typing import List, Dict, Any, Optional
from core.session.models import SessionModel, MessageModel, SessionGraphModel


class SessionExporter:
    """Exports research sessions and knowledge graphs into standard formats."""

    @staticmethod
    def to_markdown(
        session: SessionModel,
        messages: List[MessageModel],
        graph: SessionGraphModel,
        chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generate comprehensive scientific research dossier in Markdown."""
        date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session.updated_at))
        lines = []

        # ── Document Header
        lines.append(f"# Research Dossier: {session.title}")
        lines.append("")
        lines.append(f"**Domain:** `{session.focus_domain}` | **Mode:** `{session.research_mode}` | **Date:** {date_str}")
        lines.append(f"**Session ID:** `{session.id}` | **Total Turns:** {len(messages)} | **Graph Nodes:** {len(graph.nodes)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── Executive Summary
        lines.append("## 1. Executive Summary")
        lines.append("")
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        if assistant_msgs:
            # Use the latest assistant synthesis as primary answer summary
            latest_ans = assistant_msgs[-1].content
            # Take first 2-3 paragraphs as executive brief
            paragraphs = [p for p in latest_ans.split("\n\n") if p.strip()]
            summary_brief = "\n\n".join(paragraphs[:3])
            lines.append(summary_brief)
        else:
            lines.append("No synthesized findings available yet.")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── Chronological Research Lineage (The Journey)
        lines.append("## 2. Conversational Research Lineage & Turns")
        lines.append("")
        for idx, m in enumerate(messages):
            role_title = "OPERATOR INQUIRY" if m.role == "user" else "SYNTHESIZED FINDINGS"
            t_str = time.strftime("%H:%M:%S", time.localtime(m.created_at))
            lines.append(f"### Turn #{idx + 1}: {role_title} ({t_str})")
            if m.parent_message_id:
                lines.append(f"> *Branch parent:* `{m.parent_message_id[:12]}`")
                lines.append("")
            lines.append(m.content)
            lines.append("")

        lines.append("---")
        lines.append("")

        # ── Verifiable Claims & Evidence Matrix
        claim_nodes = [n for n in graph.nodes if n.node_type == "claim"]
        if claim_nodes:
            lines.append("## 3. Extracted Claims & Verification Matrix")
            lines.append("")
            lines.append("| Claim / Finding | Confidence | Details |")
            lines.append("| :--- | :---: | :--- |")
            for c in claim_nodes:
                conf = f"{int(c.confidence * 100)}%" if c.confidence else "N/A"
                clean_lbl = c.label.replace("|", "/")
                clean_desc = (c.description or "").replace("|", "/")[:180]
                lines.append(f"| **{clean_lbl}** | {conf} | {clean_desc} |")
            lines.append("")
            lines.append("---")
            lines.append("")

        # ── Contradictions & Disputed Findings
        contradiction_edges = [e for e in graph.edges if e.relation_type == "contradicts"]
        if contradiction_edges:
            lines.append("## 4. Contradictions & Disputed Points")
            lines.append("")
            lines.append("> [!WARNING]")
            lines.append("> The following conflicting findings or failed replications were detected:")
            lines.append("")
            for ce in contradiction_edges:
                lines.append(f"- **Conflict:** `{ce.source_node_id}` contradicts `{ce.target_node_id}`")
                if ce.evidence_text:
                    lines.append(f"  - *Evidence note:* {ce.evidence_text}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # ── Knowledge Graph Architecture (Mermaid)
        lines.append("## 5. Knowledge Graph Architecture")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph TD")
        for n in graph.nodes[:35]:  # Limit to 35 nodes to prevent mermaid blowout
            safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', n.id)
            safe_label = re.sub(r'["\[\]()]', '', n.label)[:35]
            lines.append(f'    {safe_id}["[{n.node_type.upper()}] {safe_label}"]')
        for e in graph.edges[:50]:
            safe_src = re.sub(r'[^a-zA-Z0-9_]', '_', e.source_node_id)
            safe_tgt = re.sub(r'[^a-zA-Z0-9_]', '_', e.target_node_id)
            lines.append(f'    {safe_src} -->|{e.relation_type}| {safe_tgt}')
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── Bibliography & Citations
        lines.append("## 6. Grounded Bibliography & Citations")
        lines.append("")
        all_sources = set()
        for m in messages:
            if m.metadata and "sources" in m.metadata:
                for s in m.metadata["sources"]:
                    if isinstance(s, dict):
                        url = s.get("url") or s.get("link")
                        title = s.get("title") or url
                    else:
                        url = str(s)
                        title = str(s)
                    if url:
                        all_sources.add((title, url))

        if chunks:
            for c in chunks:
                if c.get("url"):
                    all_sources.add((c.get("title") or c.get("url"), c.get("url")))

        if all_sources:
            for idx, (title, url) in enumerate(sorted(all_sources), start=1):
                clean_title = title if title != url else url.replace("https://", "").split("/")[0]
                lines.append(f"{idx}. [{clean_title}]({url})")
        else:
            lines.append("No explicit external URLs recorded.")

        lines.append("")
        lines.append("---")
        lines.append("*Generated autonomously by Zhenyi 2.0 Autonomous Research Studio*")
        return "\n".join(lines)

    @staticmethod
    def to_bibtex(
        session: SessionModel,
        chunks: Optional[List[Dict[str, Any]]] = None,
        messages: Optional[List[MessageModel]] = None,
    ) -> str:
        """Format cited research works and URLs into BibTeX (.bib) format."""
        entries = []
        seen_keys = set()
        current_year = time.strftime("%Y")

        # Harvest from chunks
        items = list(chunks or [])
        if messages:
            for m in messages:
                if m.metadata and "sources" in m.metadata:
                    for s in m.metadata["sources"]:
                        if isinstance(s, dict):
                            items.append(s)
                        elif isinstance(s, str):
                            items.append({"title": s.split("/")[-1] or s, "url": s, "source": "web"})

        for idx, item in enumerate(items, start=1):
            title = str(item.get("title") or f"Research Work {idx}").strip()
            url = str(item.get("url") or "").strip()
            doi = str(item.get("doi") or "").strip()
            source = str(item.get("source") or "web").lower()
            authors = item.get("authors") or []
            year = item.get("published") or current_year

            # Clean key
            slug = re.sub(r'[^a-zA-Z0-9]', '', title[:15]).lower() or f"ref{idx}"
            cite_key = f"zhenyi_{slug}_{idx}"
            if cite_key in seen_keys:
                continue
            seen_keys.add(cite_key)

            author_str = " and ".join(authors[:4]) if authors else "Zhenyi Research Agent"

            entry_lines = [f"@misc{{{cite_key},"]
            entry_lines.append(f'  title = {{{{{title}}}}},')
            entry_lines.append(f'  author = {{{author_str}}},')
            entry_lines.append(f'  year = {{{year[:4] if year else current_year}}},')
            if url:
                entry_lines.append(f'  howpublished = {{\\url{{{url}}}}},')
            if doi:
                entry_lines.append(f'  doi = {{{doi}}},')
            entry_lines.append(f'  note = {{Retrieved via Zhenyi 2.0 ({source})}}')
            entry_lines.append("}")
            entries.append("\n".join(entry_lines))

        if not entries:
            entries.append(f"@misc{{zhenyi_{session.id},\n  title = {{{{{session.title}}}}},\n  year = {{{current_year}}},\n  note = {{Zhenyi Research Investigation}}\n}}")

        return "\n\n".join(entries)

    @staticmethod
    def to_obsidian_canvas(
        session: SessionModel,
        graph: SessionGraphModel
    ) -> Dict[str, Any]:
        """Convert session Knowledge Graph to spatial Obsidian Canvas JSON (.canvas)."""
        nodes_out = []
        edges_out = []

        cols = max(3, int(len(graph.nodes) ** 0.5) + 1)
        card_w, card_h = 300, 160
        gap_x, gap_y = 60, 60

        type_colors = {
            "entity": "1",      # Red/Rose
            "claim": "2",       # Orange/Amber
            "source": "4",      # Green/Emerald
            "hypothesis": "5",  # Blue/Cyan
        }

        for i, n in enumerate(graph.nodes):
            col = i % cols
            row = i // cols
            x = col * (card_w + gap_x)
            y = row * (card_h + gap_y)

            text_content = f"### [{n.node_type.upper()}] {n.label}\n\n{n.description or ''}"
            if n.confidence:
                text_content += f"\n\n*Confidence:* {int(n.confidence * 100)}%"

            nodes_out.append({
                "id": n.id,
                "x": x,
                "y": y,
                "width": card_w,
                "height": card_h,
                "type": "text",
                "text": text_content,
                "color": type_colors.get(n.node_type, "0"),
            })

        for e in graph.edges:
            edges_out.append({
                "id": e.id,
                "fromNode": e.source_node_id,
                "fromSide": "bottom",
                "toNode": e.target_node_id,
                "toSide": "top",
                "label": e.relation_type,
                "color": "1" if e.relation_type == "contradicts" else "0",
            })

        return {
            "nodes": nodes_out,
            "edges": edges_out,
        }
