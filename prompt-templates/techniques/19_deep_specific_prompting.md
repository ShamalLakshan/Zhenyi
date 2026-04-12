# Technique 19: Deep Specific Prompting for Research Analysis

## Overview
Deep Specific Prompting ensures that models produce expert-level, concrete answers rather than shallow summaries. It requires models to extract and emphasize **specific facts, data points, contradictions, and limitations** rather than generic platitudes.

## Problem: Generic Shallow Outputs
Traditional minimal prompts produce shallow, generic answers:
- "The market is growing" (no numbers, timeline, or sources)
- "Many believe this is important" (vague generalities)
- "Sources may have different views" (contradictions not explicit)
- No clear distinction between well-established facts and uncertain claims

## Solution: Explicit Specificity Requirements
Instruct models to:
1. **Extract CONCRETE FACTS** — names, numbers, versions, dates, part numbers, specifications, prices, authors, institutions
2. **Note source agreements AND contradictions** — don't hide disagreements; make them explicit
3. **Flag uncertainty** — distinguish between verified claims and speculative statements
4. **Avoid filler** — every finding must have measurable value

---

## Example: Before vs After

### BEFORE — Generic Prompt
```
You are a research analyst. Analyse the provided sources for the query below.

QUERY: {query}
SOURCES: {context}

Respond with ONLY valid JSON:
{
  "confidence": <float 0.0-1.0>,
  "key_findings": ["finding 1", "finding 2"],
  "contradictions": ["contradiction if any, else empty list"],
  "needs_more_info": ["gap if any, else empty list"]
}
```

**Output (shallow):**
```json
{
  "confidence": 0.6,
  "key_findings": [
    "The technology is advancing",
    "There is growing interest in the field"
  ],
  "contradictions": [],
  "needs_more_info": ["More details on adoption rates"]
}
```

### AFTER — Deep Specific Prompt
```
You are a specialist research analyst with deep domain expertise. Your job is to extract 
maximum useful information from these sources.

RESEARCH QUERY: {query}
SOURCES: {context}

Instructions:
- Extract SPECIFIC facts: names, numbers, versions, dates, part numbers, specifications, 
  prices, authors, institutions — not generalities
- Note direct quotes or data points from sources where relevant
- Identify what sources AGREE on and what they CONTRADICT
- Flag any claims that lack a source or seem uncertain
- Do NOT pad with filler. Every finding must be a concrete, specific claim.

Respond ONLY with valid JSON, no markdown, no preamble:
{
  "confidence": <float 0.0-1.0 based on source quality and agreement>,
  "key_findings": [
    "Specific finding with concrete detail — not a vague summary",
    "Another specific finding"
  ],
  "contradictions": ["Source A says X but source B says Y — be explicit"],
  "needs_more_info": ["Specific gap that would improve the answer"]
}
```

**Output (deep & specific):**
```json
{
  "confidence": 0.8,
  "key_findings": [
    "Apache Spark 3.5.0 released March 2024 with 40% performance improvement on ML workloads (source: databricks.com)",
    "Ray AI Runtime adopted by Uber, Lyft, and Shopify (source: ray.io case studies)",
    "Llama 3 70B inference cost dropped to $0.90 per million tokens on Together AI (source: together.ai pricing)"
  ],
  "contradictions": [
    "TensorFlow claims best-in-class distributed training; PyTorch community reports better real-world scaling (sources: tensorflow.org vs pytorch.org benchmarks from different teams, 2024)"
  ],
  "needs_more_info": [
    "Quantitative comparison of energy consumption across frameworks",
    "Adoption rates by enterprise size and industry"
  ]
}
```

---

## Key Principles

### 1. Concreteness Over Abstraction
- ❌ "Several studies show this is effective"
- ✅ "Smith et al. (2024) measured a 35% improvement in [metric] using [method]"

### 2. Contradiction Handling
- ❌ Smooth over conflicts; present both views separately
- ✅ Explicitly state: "Source A claims X, but Source B measured Y — these disagree because..."

### 3. Source Attribution
- ❌ Generic findings with no source
- ✅ "According to [source], [specific claim with detail]"

### 4. Confidence Grounding
- Base confidence on **source quality** and **agreement level**:
  - 0.9+ = Multiple authoritative sources agree on specific data
  - 0.7–0.89 = Primary sources agree but some limitations or dissent
  - 0.5–0.69 = Mixed evidence, contradictions present, or limited source count
  - <0.5 = Scarce, conflicting, or unreliable sources

### 5. Explicit Limits
- Always list gaps: "Would improve answer: [specific data needed]"
- Flag unverified claims: "Claimed but not independently verified"

---

## Application to Multi-Agent Research Pipelines

### Analyst Agent
Uses deep specificity to extract actionable findings from chunks:
- Identifies exact claims with citations
- Notes contradictions between sources
- Quantifies confidence based on evidence quality

### Synthesizer Agent
Builds on analyst specificity:
- Leads with most important facts (not filler)
- Includes concrete details: numbers, versions, dates
- Explicitly addresses contradictions (doesn't smooth over)
- States what is well-established vs contested or uncertain
- Writes as the expert directly answering, not as an aggregator

### Triage Agent
Uses specificity criteria to evaluate source quality:
- 10: Source provides specific, verifiable information directly answering the query
- 7–9: Highly relevant, contains useful specific details
- 4–6: Tangentially related or too general
- 1–3: Barely related
- 0: Irrelevant or spam

---

## When to Use Deep Specific Prompting

✅ **Use for:**
- Research analysis where precision matters
- Multi-source synthesis requiring contradiction detection
- Expert-level Q&A where vague answers are useless
- Technical or niche topics requiring concrete facts
- Domains where false specificity is worse than admitting limits

❌ **May be overkill for:**
- Simple factual lookups (e.g., "What is the capital of France?")
- Broad creative brainstorming (though even here, specificity helps)
- Conversational chatbot responses where users expect warmth over precision

---

## See Also
- Technique 01: Role Prompting
- Guardrail 01: Prompt-Based (format/structure constraints)
- Guardrail 04: Research Agent Prompts (complete examples)
