# Guardrail 04: Research Agent Prompts — Deep Analysis & Specificity

## Overview
This guardrail demonstrates how the three core agent prompts (analyst, synthesizer, triage) enforce deep analysis and specificity through prompt-based instruction. These prompts build on role-prompting (Technique 01) and combine multiple guardrail strategies: format constraints (Guardrail 01), explicit instruction, and confidence grounding.

## Architecture
Three agents work together in a pipeline:

```
Triage Agent (scores chunks)
    ↓
Analyst Agents (extracts specific findings)
    ↓
Synthesizer Agent (combines into expert answer)
```

Each agent enforces guardrails through its prompt to ensure:
1. **Specificity**: Concrete facts, not generalities
2. **Contradiction Detection**: Explicit conflict identification
3. **Confidence Calibration**: Evidence-based confidence scoring
4. **Format Correctness**: JSON structure or simple integer output

---

## 1. Triage Agent — Source Quality Gate

**Role**: Scores each scraped chunk 0–10 for relevance and specificity.

**Prompt**:
```
You are a research librarian deciding whether a source is worth an expert's time.

RESEARCH QUERY: {query}
SOURCE CONTENT: {content_preview}

Score this source's relevance and usefulness to the query:
10 = directly answers the query with specific, verifiable information
7-9 = highly relevant, contains useful specific details
4-6 = tangentially related or too general
1-3 = barely related
0 = completely irrelevant or spam

Reply with ONLY a single integer 0-10. Nothing else.
```

**Guardrails Enforced**:
- **Role clarity**: "research librarian" — suggests expert judgment, not surface-level filtering
- **Rubric explicitness**: 0–10 scale with clear semantics tied to specificity ("specific, verifiable" vs "too general")
- **Format constraint**: "single integer 0-10. Nothing else." — forces clean output parseable as float
- **Precision emphasis**: Scores reward sources with "specific details" (7-9) over "too general" (4-6)

**Output Format**: Single integer, e.g., `8`

---

## 2. Analyst Agent — Specific Finding Extraction

**Role**: Receives filtered chunks and extracts concrete findings, contradictions, confidence.

**Prompt**:
```
You are a specialist research analyst with deep domain expertise. Your job is to 
extract maximum useful information from these sources.

RESEARCH QUERY: {query}

SOURCES:
{context}

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

**Guardrails Enforced**:
- **Role establishment**: "specialist research analyst with deep domain expertise" → legitimacy and depth expectation
- **Explicit specificity instruction**: "Extract SPECIFIC facts: names, numbers, versions..." — concrete examples of what counts as specific
- **Contradiction detection mandate**: "Identify what sources AGREE on and what they CONTRADICT" — forces active contradiction checking
- **Filler prohibition**: "Do NOT pad with filler. Every finding must be a concrete, specific claim." — removes disclaimers and generalities
- **Confidence grounding**: "based on source quality and agreement" — ties confidence to evidence, not model uncertainty
- **Format constraint**: JSON schema with required fields enforces structured output
- **JSON-only rule**: "ONLY valid JSON, no markdown, no preamble" — no excuse for unparseable text

**Output Format**: Structured JSON; parser falls back gracefully on malformed but extractable results

---

## 3. Synthesizer Agent — Expert Integration

**Role**: Combines analyst findings into a comprehensive, expert-level answer.

**Prompt**:
```
You are a senior research synthesizer. Your output will be read by someone who needs 
comprehensive, expert-level information — not a summary a general chatbot would give.

QUERY: {query}

ANALYST FINDINGS:
{findings_block}

[CONTRADICTIONS NOTED: (if any contradictions exist)]
{contradictions_block}

Write a comprehensive answer following these rules:
1. Lead with the most important specific facts directly relevant to the query
2. Include concrete details: numbers, names, specifications, versions, dates
3. Structure with clear sections if the answer covers multiple aspects
4. Explicitly address contradictions — do not smooth them over
5. State what is well-established vs what is uncertain or contested
6. Do NOT use phrases like 'based on the findings' or 'the analysts found' — 
   write as if you are the expert, directly answering the question
7. Minimum 3 paragraphs. Maximum depth the data supports.

End your response with exactly this line:
CONFIDENCE: <decimal 0.0 to 1.0>
```

**Guardrails Enforced**:
- **Audience clarity**: "someone who needs comprehensive, expert-level information" → raises quality bar above generic summaries
- **Specificity prioritization**: "Lead with the most important specific facts" and "Include concrete details" — forces front-loading of value
- **Contradiction handling mandate**: "Explicitly address contradictions — do not smooth them over" — prevents false consensus
- **Uncertainty distinction**: "State what is well-established vs what is uncertain or contested" — nuanced confidence communication
- **Expert tone enforcement**: "write as if you are the expert" — rejects aggregator/summarizer language ("based on the findings", "analysts found")
- **Depth requirement**: "Minimum 3 paragraphs" — prevents truncation to shallow summaries
- **Confidence extraction**: "End your response with exactly this line: CONFIDENCE:" — parseable confidence signal
- **Structured presentation**: "clear sections if answer covers multiple aspects" — readability + logical organization

**Output Format**: Free-form prose with structured sections, ending with parseable confidence line

---

## Data Flow & Guardrail Coordination

```
Query + Scraped Chunks
    ↓
[Triage Agent]
  Prompt: "Score relevance 0-10, specific > general"
  Guardrail: Format (single int) + specificity emphasis
    ↓ (filters to chunks ≥ threshold)
[Analyst Agents] (1–4 agents may run in parallel)
  Prompt: "Extract SPECIFIC facts, flag contradictions, confidence based on agreement"
  Guardrails: Specificity (names, numbers, refs), contradiction detection, 
             confidence grounding, JSON format
    ↓
{findings_block, contradictions_block, confidence_scores}
    ↓
[Synthesizer Agent]
  Prompt: "Integrate findings expertly, lead with specifics, don't hide contradictions,
           distinguish established vs uncertain"
  Guardrails: Expert tone, contradiction handling, specificity, depth minimum, 
             confidence extraction
    ↓
Final Answer + Confidence
```

---

## Key Guardrail Patterns

### Pattern 1: Specificity via Enumeration
**Problem**: "Be specific" is vague.
**Solution**: List examples of specificity:
```
"Extract SPECIFIC facts: names, numbers, versions, dates, part numbers, 
specifications, prices, authors, institutions — not generalities"
```

### Pattern 2: Contradiction Detection via Instruction
**Problem**: Models may hide or average contradictions.
**Solution**: Mandate and exemplify:
```
"Identify what sources AGREE on and what they CONTRADICT"
"contradictions": ["Source A says X but source B says Y — be explicit"]
```

### Pattern 3: Confidence Grounding
**Problem**: Confidence can reflect model uncertainty, not evidence quality.
**Solution**: Define confidence basis explicitly:
```
"confidence": <float 0.0-1.0 based on source quality and agreement>
```

### Pattern 4: Format Constraint as Guardrail
**Problem**: Models may ramble or hedge with commentary.
**Solution**: Strict format requirements:
```
"Respond ONLY with valid JSON, no markdown, no preamble"
"Reply with ONLY a single integer 0-10. Nothing else."
"End your response with exactly this line: CONFIDENCE: <decimal>"
```

### Pattern 5: Filler Prohibition
**Problem**: Models pad answers with disclaimers ("It depends", "Further research needed").
**Solution**: Explicit prohibition + explanation:
```
"Do NOT pad with filler. Every finding must be a concrete, specific claim."
```

### Pattern 6: Role-Based Expertise (Technique 01 Integration)
**Problem**: Generic "assistant" tone produces generic answers.
**Solution**: Specific role with high stakes:
```
"You are a specialist research analyst with deep domain expertise"
"You are a senior research synthesizer. Your output will be read by someone 
who needs comprehensive, expert-level information"
"You are a research librarian deciding whether a source is worth an expert's time"
```

---

## Testing & Validation

### Triage Agent Test
```
Query: "What is the latest GPU model from NVIDIA?"
Content: "NVIDIA is a leading company in AI."  [Too general]
Expected score: 3–5 (tangential, not specific)

Content: "NVIDIA released the H200 with 141GB HBM3E memory on March 21, 2024."  [Specific]
Expected score: 9–10 (specific, verifiable, answers query)
```

### Analyst Agent Test
```
Query: "How does LLM fine-tuning affect training time?"
Sources:
  - "Fine-tuning is fast"  [vague]
  - "GPT-3.5 fine-tuning takes 45 minutes per epoch on 4× A100 GPUs using LoRA"  [specific]
  - "Fine-tuning can be done quickly, though results vary"  [vague]

Expected key_findings:
  ✓ "Fine-tuned GPT-3.5 with LoRA completes one epoch in 45 minutes on 4× A100 GPUs"
  ✗ "Fine-tuning is fast" (too vague)

Expected contradictions: [] (all source are consistent or vague)
```

### Synthesizer Agent Test
```
Analyst findings:
  - "Llama 2 released July 2023" [Source: Meta]
  - "Llama 3 released April 2024" [Source: Meta]
  - "Llama 3 inference 2x faster than 2" [Source: Some community benchmark]
  - "Speed gains marginal in production" [Source: Another community report]

Expected synthesizer answer:
  - Leads with timeline (July 2023 → April 2024)
  - Cites specific speedup claim and contradicting report
  - Distinguishes: Meta's official release dates (established) vs 
    community speed benchmarks (contested, variable setup)
  - Ends with confidence reflecting agreement on dates but dispute on performance
```

---

## Integration with Fallback Scraper Selection (Orchestrator)

When the Orchestrator LLM (Gemini) is rate-limited, the fallback plan uses heuristic scraper selection based on query keywords:

- **"latest", "news", "2024"** → `["hackernews", "web"]` (ensures current sources for triage)
- **"spec", "datasheet", "product"** → `["web", "hackernews"]` (prioritizes web for specific docs)
- **Long queries (>8 words)** → `["hackernews", "web"]` (complex questions need breadth)

This ensures Triage/Analyst agents receive higher-quality, query-relevant sources even when Orchestrator falls back.

---

## References
- **Technique 01**: Role Prompting (foundation)
- **Technique 02**: Chain of Thought (used implicitly in analyst reasoning)
- **Guardrail 01**: Prompt-Based (format & structure constraints)
- **Technique 19**: Deep Specific Prompting (detailed specificity strategies)
