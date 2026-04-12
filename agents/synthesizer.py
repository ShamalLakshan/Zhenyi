"""
Synthesizer Agent
─────────────────
Takes all analyst outputs and produces a final, coherent answer.
Designed for Cohere (RAG-optimised) but works with any provider.
Extracts confidence from response. Handles missing/empty analyst outputs.
"""

import logging
from agents.base_agent import BaseAgent
from core.key_pool import KeyPool

logger = logging.getLogger(__name__)


class SynthesizerAgent(BaseAgent):

    def __init__(self, pool: KeyPool, provider: str, model: str):
        super().__init__("synthesizer", pool, provider=provider, model=model)

    async def synthesize(
        self,
        query: str,
        analyst_outputs: list[dict],
        query_id: str = "",
    ) -> dict:
        """
        Merge analyst findings into a final answer with confidence score.
        Returns a dict with 'answer' and 'confidence' always set.
        """
        if not analyst_outputs:
            return {
                "answer": "No analyst data available to synthesize.",
                "confidence": 0.0,
            }

        findings_block = self._format_findings(analyst_outputs)
        contradictions_block = self._format_contradictions(analyst_outputs)

        prompt = (
            f"You are a senior research synthesizer. Your output will be read "
            f"by someone who needs comprehensive, expert-level information — not "
            f"a summary a general chatbot would give.\n\n"
            f"QUERY: {query}\n\n"
            f"ANALYST FINDINGS:\n{findings_block}\n"
        )
        if contradictions_block:
            prompt += f"CONTRADICTIONS NOTED:\n{contradictions_block}\n"
        else:
            prompt += ""

        prompt += (
            f"\nWrite a comprehensive answer following these rules:\n"
            f"1. Lead with the most important specific facts directly relevant to the query\n"
            f"2. Include concrete details: numbers, names, specifications, versions, dates\n"
            f"3. Structure with clear sections if the answer covers multiple aspects\n"
            f"4. Explicitly address contradictions — do not smooth them over\n"
            f"5. State what is well-established vs what is uncertain or contested\n"
            f"6. Do NOT use phrases like 'based on the findings' or 'the analysts found' "
            f"— write as if you are the expert, directly answering the question\n"
            f"7. Minimum 3 paragraphs. Maximum depth the data supports.\n\n"
            f"End your response with exactly this line:\n"
            f"CONFIDENCE: <decimal 0.0 to 1.0>"
        )

        raw = await self.call(prompt, query_id=query_id, estimated_tokens=1200)

        if not raw:
            # Build minimal answer from raw findings
            fallback = "\n".join(
                f for out in analyst_outputs
                for f in out.get("key_findings", [])
            ) or "No findings available."
            return {"answer": fallback, "confidence": 0.3}

        return self._extract_answer_and_confidence(raw)

    def _format_findings(self, outputs: list[dict]) -> str:
        lines = []
        for i, out in enumerate(outputs):
            provider = out.get("provider", f"analyst_{i}")
            for finding in out.get("key_findings", []):
                lines.append(f"[{provider.upper()}] {finding}")
        return "\n".join(lines) if lines else "No findings."

    def _format_contradictions(self, outputs: list[dict]) -> str:
        lines = []
        for out in outputs:
            for c in out.get("contradictions", []):
                if c:
                    lines.append(f"  - {c}")
        return "\n".join(lines)

    def _extract_answer_and_confidence(self, raw: str) -> dict:
        confidence = 0.5
        answer = raw.strip()

        if "CONFIDENCE:" in raw:
            parts = raw.rsplit("CONFIDENCE:", 1)
            answer = parts[0].strip()
            conf_raw = parts[1].strip().split()[0] if parts[1].strip() else ""
            confidence = self.parse_float(conf_raw, default=0.5)
            confidence = max(0.0, min(1.0, confidence))

        return {"answer": answer, "confidence": confidence}
