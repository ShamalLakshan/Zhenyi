# Zhenyi Architecture

## Overview

Zhenyi is a multi-agent research orchestration system that combines dynamic LLM selection, intelligent web scraping, and hierarchical content filtering to produce comprehensive research answers.

The system processes queries through a 5-stage pipeline, where each stage is handled by specialized agents with automatic fallback mechanisms.

## Pipeline Architecture

The core execution flow consists of five sequential stages:

```
1. Orchestrator Planning
   ↓
2. Scraper Execution (Parallel)
   ↓
3. Triage Filtering
   ↓
4. Analyst Processing (Parallel)
   ↓
5. Synthesis
```

### Stage 1: Orchestrator Planning

**Agent**: Gemini LLM  
**Role**: Analyze query and determine research strategy

The orchestrator:
- Detects query intent from 9 categories (weather, finance, academic, etc.)
- Selects appropriate scraper set based on intent
- Assigns specialized roles to available LLM providers
- Determines triage mode (scraper_only, llm_only, or hybrid)
- Outputs a structured plan with: profile, scrapers, analyst assignments

**Profiles**:
- `simple_factual` - Definitions/facts; no scraping needed
- `current_factual` - Recent news/status; 1-2 scrapers
- `research` - Multi-source; 2-3 scrapers
- `deep_research` - Complex/multi-domain; all suggested scrapers

**Output**: JSON plan with assigned providers and scraper list

### Stage 2: Scraper Execution

**Registry**: Parallel scraper invocation  
**Role**: Collect raw data from web sources

Scrapers run concurrently and return:
- `content` - Main text/data
- `source` - Origin identifier
- `title` - Document title
- `url` - Source URL (for citation)

**Built-in scrapers**:
- `hackernews` - Recent tech news
- `web` - DuckDuckGo search results
- `arxiv` - Academic papers
- `wikipedia` - General knowledge
- `youtube` - Video descriptions
- `sec_edgar` - Financial filings
- `openalex` - Academic metadata
- `open_meteo` - Weather/climate data
- `ddgs` - Web search

Each scraper implements circuit breaker pattern: fails gracefully after 3 consecutive errors.

**Output**: List of raw chunks with metadata

### Stage 2b: LLM Perspectives (Optional)

**Role**: Generate LLM-based perspectives as additional chunks

When multiple analysts are assigned, the system calls 1-2 analysts to generate perspective chunks. These are treated as regular chunks and go through triage alongside scraper data.

This ensures LLM reasoning contributes to the triaged data pool.

**Output**: LLM-generated chunks merged with scraper data

### Stage 3: Triage

**Agent**: Assigned triage provider from key pool  
**Role**: Score and filter chunks for relevance

Triage evaluates relevance on 0-10 scale. Modes:

- **scraper_only**: Fast heuristic scoring (keyword matching, source quality)
- **llm_only**: LLM-based scoring (slower, higher accuracy)
- **hybrid**: Heuristic for all chunks; LLM augmentation for borderline (3-8 score range)

Chunks below threshold (default: 6) are dropped.

**Input**: Raw chunks + LLM perspectives  
**Output**: Scored chunks above threshold

### Stage 4: Analyst Processing

**Agents**: 1-4 analyst providers from key pool  
**Role**: Deep analysis of filtered chunks

Analysts work in parallel, each receiving:
- The full query
- Their assigned chunk slice
- Instructions for key findings extraction

Each analyst returns structured findings with:
- Key findings
- Reasoning chain
- Confidence score

**Output**: Analyst results merged

### Stage 5: Synthesis

**Agent**: Assigned synthesizer provider  
**Role**: Integrate findings into coherent answer

Synthesizer receives:
- Original query
- All analyst outputs
- Source metadata

Produces final answer with:
- Comprehensive response
- Confidence score
- Citation support

**Output**: Final answer, confidence, sources

## Key Pool Management

Located in `core/key_pool.py`

**Features**:
- Tracks available API keys from 6+ providers
- Monitors daily usage and remaining quota
- Supports automatic provider fallback on exhaustion
- Real-time provider capability snapshot

**Providers supported**:
- Google Gemini
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Groq (Llama variants)
- Hugging Face
- Together AI

**Key rotation**:
- Automatic selection of highest-availability provider per role
- Prioritizes providers with highest remaining daily quota
- Supports weighted selection based on provider strengths

## Event Bus

Located in `core/events.py`

Real-time event emission for frontend updates:

**Event types**:
- `ORCHESTRATOR_STARTED` - Planning stage begins
- `ORCHESTRATOR_DONE` - Plan complete
- `SCRAPER_STARTED` - Scraping begins
- `CHUNKS_COLLECTED` - Raw data collected
- `SCRAPER_DONE` - All scrapers finished
- `TRIAGE_STARTED` - Filtering begins
- `CHUNKS_SCORED` - Relevance scoring complete
- `CHUNKS_FILTERED` - Final filtered set
- `ANALYST_STARTED` - Analysis begins
- `ANALYST_DONE` - Analysis complete
- `SYNTHESIZER_STARTED` - Synthesis begins
- `QUERY_DONE` - Pipeline complete

Frontend subscribes via WebSocket to receive real-time updates.

## Data Persistence

Located in `core/state_store.py` and `core/debug_store.py`

**Query Storage** (zhenyi.db):
- Query metadata (ID, text, timestamp)
- Execution plan
- Final answer and confidence
- Source citations
- Duration metrics

**Debug Storage**:
- API request/response logs (redacted)
- Agent reasoning chains
- Scraper invocations and outputs
- Performance metrics per stage

## Error Handling

**Circuit Breaker Pattern** (base_scraper.py):
- Scraper fails 3 times → marked OPEN
- Prevents cascade failures
- Graceful degradation with partial results

**Provider Fallback** (key_pool.py):
- Role assignment fails → next available provider selected
- Exhausted keys → automatic rotation
- All keys unavailable → system returns error

**Stage Isolation**:
- Scraper failure → pipeline continues with empty chunks
- Triage failure → all chunks passed through
- Analyst failure → partial results used
- Synthesis failure → analyst findings returned directly

## Configuration

Located in `agents.yaml`

**Structure**:
```yaml
providers:
  gemini:
    keys: [GEMINI_KEY_1, GEMINI_KEY_2]
    strengths: [orchestration, reasoning]
    models:
      default: gemini-2.0-flash
      others: [...]
  
  groq:
    keys: [GROQ_KEY_1]
    strengths: [speed, general]
    models:
      default: llama-3.1-8b-instant
      others: [...]
```

**Scraper Registry**:
```yaml
scrapers:
  hackernews:
    enabled: true
    rate_limit: 100
    timeout: 15
```

## Extending the System

### Adding a New Scraper

1. Create `scrapers/my_scraper.py` implementing `BaseScraper`
2. Implement `async def scrape(query: str) -> list[dict]`
3. Register in `scrapers/registry.py`
4. Add configuration to `agents.yaml`

### Adding a New Agent Role

1. Create `agents/my_agent.py` extending `BaseAgent`
2. Implement role-specific `async def` methods
3. Update orchestrator prompt to assign role
4. Register instantiation in `core/pipeline.py`

### Adding a New LLM Provider

1. Create provider integration in `core/key_pool.py`
2. Update `agents/base_agent.py` to support provider
3. Add provider configuration to `agents.yaml`
4. Test fallback mechanisms

## Performance Characteristics

- **Orchestrator Planning**: 1-3 seconds (Gemini call)
- **Scraping**: 5-30 seconds (parallel, depends on scraper count)
- **Triage**: 1-10 seconds (depends on chunk count and mode)
- **Analysis**: 5-20 seconds (parallel analyst calls)
- **Synthesis**: 2-5 seconds (integrate and respond)

**Total**: Typically 20-60 seconds for full deep_research query

## Limitations

- Scraper availability depends on target website stability
- API key quotas limit daily query volume
- Large result sets require pagination (max 20 chunks by default)
- Some providers have latency variations
- Geographic restrictions on some scrapers (SEC Edgar US-only)
