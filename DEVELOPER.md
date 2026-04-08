# LLM Research Council — Developer Documentation

> Complete reference for anyone continuing or extending this project.

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Architecture Overview](#2-architecture-overview)
3. [Data Flow — Step by Step](#3-data-flow--step-by-step)
4. [File Reference](#4-file-reference)
5. [Key Design Decisions](#5-key-design-decisions)
6. [Configuration Reference](#6-configuration-reference)
7. [Adding API Keys](#7-adding-api-keys)
8. [Adding a New Scraper](#8-adding-a-new-scraper)
9. [Adding a New LLM Provider](#9-adding-a-new-llm-provider)
10. [Database Schema](#10-database-schema)
11. [Error Handling Philosophy](#11-error-handling-philosophy)
12. [Known Limitations and Workarounds](#12-known-limitations-and-workarounds)
13. [CLI Commands](#13-cli-commands)
14. [Debugging Guide](#14-debugging-guide)
15. [Extending the Pipeline](#15-extending-the-pipeline)

---

## 1. What This Project Is

A multi-LLM research agent that uses **only free-tier API keys**. When you ask
it a question, it:

- Dynamically assigns roles (triage, analyst, synthesizer) to whichever LLM
  providers are currently available and have quota remaining
- Scrapes live data from HackerNews, Reddit, and the web
- Runs multiple analysts in parallel on different slices of the scraped data
- Synthesizes a final answer with confidence score

The central thesis: **a weaker model with good orchestration beats a single
expensive model**, because it reads fresher data and cross-checks findings.

**What it is NOT:**
- A chatbot (no memory between queries)
- A replacement for deep academic research
- Production-ready for high traffic (free tiers are the constraint)

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  USER INPUT                                                          │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Orchestrator (Gemini)  │◄── Key Pool Scheduler
                    │   Reads live snapshot    │
                    │   Produces execution plan│
                    └────────────┬────────────┘
                                 │  plan: {profile, scrapers, roles}
         ┌───────────────────────┼──────────────────────┐
         │                       │                      │
    ┌────▼────┐           ┌──────▼──────┐        ┌─────▼──────┐
    │HN       │           │Reddit       │        │Web          │
    │Scraper  │           │Scraper      │        │Scraper      │
    └────┬────┘           └──────┬──────┘        └─────┬──────┘
         └───────────────────────┼──────────────────────┘
                                 │  raw chunks
                    ┌────────────▼────────────┐
                    │   Triage Agent           │
                    │   Scores 0-10 per chunk  │
                    │   Drops below threshold  │
                    └────────────┬────────────┘
                                 │  filtered chunks → SQLite
              ┌──────────────────┼──────────────────┐
              │                  │                  │
       ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
       │  Analyst A   │   │  Analyst B   │   │  Analyst C  │
       │  (chunk 1/3) │   │  (chunk 2/3) │   │ (chunk 3/3) │
       └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
              └──────────────────┼──────────────────┘
                                 │  findings JSON from each
                    ┌────────────▼────────────┐
                    │   Synthesizer (Cohere)   │
                    │   Merges all findings    │
                    │   Outputs answer +       │
                    │   confidence score       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   USER OUTPUT            │
                    │   answer, sources,       │
                    │   confidence, plan used  │
                    └─────────────────────────┘

Key Pool Scheduler (runs alongside everything)
┌──────────────────────────────────────────────────┐
│  For each provider: [key1, key2, key3...]         │
│  Each key tracks: rpm_used, daily_used, cooldown  │
│  pick() returns best ready key or None            │
│  On 429: marks key in cooldown, caller retries    │
└──────────────────────────────────────────────────┘

SQLite State Store (written throughout)
┌──────────────────────────────────────────────────┐
│  chunks       — every scraped + filtered chunk    │
│  agent_outputs— every LLM call result             │
│  thought_chain— full lineage of every step        │
│  queries      — final results for history         │
└──────────────────────────────────────────────────┘
```

---

## 3. Data Flow — Step by Step

### Stage 0 — Config load
`main.py` creates a `KeyPool` from `agents.yaml`. The pool reads env var names
from yaml, then looks up actual key values from `.env` at call time (keys are
never stored in memory beyond the moment of use).

### Stage 1 — Orchestrator planning
`OrchestratorAgent.plan()` calls:
1. `pool.get_orchestrator_key()` → returns `(api_key_value, model, key_state)`
2. `pool.get_capabilities_snapshot()` → live dict of providers with quota info
3. Calls Gemini with the query + snapshot
4. Parses the JSON plan. If parse fails, `_fallback_plan()` runs without LLM.
5. `_validate_and_fix_plan()` repairs any invalid provider or model references.

**On Gemini 429:** extracts `retry_delay` seconds from the error string, calls
`key_state.set_cooldown(delay)`, immediately returns fallback plan. Next query
will see the key as not ready and skip it.

### Stage 2 — Scraping
`ScraperRegistry.run(names, query)` runs the requested scrapers concurrently
via `asyncio.gather`. Each scraper is wrapped in `BaseScraper.scrape()` which:
- Checks the circuit breaker (skips if open)
- Enforces `asyncio.wait_for()` timeout
- On failure: increments `_consecutive_failures`, opens circuit after 3

**HackerNews query distillation:** long natural-language queries return 0
results from Algolia. The scraper extracts keywords (removing stopwords), then
tries: `[top_5_keywords, keyword1, keyword2, keyword3]` in order until it
has enough results.

### Stage 3 — Triage
`TriageAgent.score_chunks()` calls the assigned LLM once per chunk with a
~200-token prompt asking for a 0-10 score. Chunks scoring below
`thresholds.relevance_min_score` (default: 6) are dropped. If all chunks are
dropped, the top 3 are kept as a safety net.

### Stage 4 — Parallel analysis
`asyncio.gather` runs all analyst agents concurrently. Each analyst gets a
slice of the scored chunks. The JSON contract every analyst must return:
```json
{
  "confidence": 0.75,
  "key_findings": ["finding 1", "finding 2"],
  "contradictions": ["any contradictions noted"],
  "needs_more_info": ["gaps in the data"]
}
```
If JSON parsing fails, the raw text is wrapped as a finding rather than lost.

### Stage 5 — Synthesis
`SynthesizerAgent.synthesize()` builds a single prompt from all analyst
findings and asks for a comprehensive answer ending with `CONFIDENCE: X.XX`.
The synthesizer strips the confidence value and stores separately.

### Stage 6 — Output
Pipeline returns:
```python
{
    "query_id":    "8-char UUID prefix",
    "profile":     "research",
    "answer":      "...",
    "confidence":  0.78,
    "sources":     ["url1", "url2"],
    "plan":        {...},     # full orchestrator plan used
    "duration_ms": 45230.0,
}
```

---

## 4. File Reference

```
council/
│
├── main.py                     Entry point. CLI loop, output formatting,
│                               /status /history /chain commands.
│
├── agents.yaml                 ALL configuration. Provider capabilities,
│                               key env var names, scraper settings,
│                               pipeline thresholds.
│
├── .env                        Actual API key values. Never commit this.
├── .env.example                Template — copy this to .env.
├── requirements.txt            Python package dependencies.
│
├── core/
│   ├── exceptions.py           Custom exception hierarchy. All non-fatal.
│   ├── key_pool.py             Key state tracking. Central scheduler.
│   │                           KeyState: tracks rpm/daily usage + cooldown.
│   │                           KeyPool: pick(), get_capabilities_snapshot().
│   ├── state_store.py          Async SQLite. save_chunks(), log_agent_output(),
│   │                           log_thought(), save_query_result().
│   └── pipeline.py             Orchestrates all 5 stages. Each stage is
│                               wrapped in try/except — one failure never
│                               stops the pipeline.
│
├── agents/
│   ├── base_agent.py           BaseAgent class. _call_provider() routes to
│   │                           correct SDK. Retry with backoff. JSON parser.
│   ├── orchestrator.py         OrchestratorAgent. Gemini-only. Produces plan.
│   │                           Falls back without LLM on any error.
│   ├── triage.py               TriageAgent. Scores chunks 0-10.
│   ├── analyst.py              AnalystAgent. Returns structured JSON findings.
│   └── synthesizer.py          SynthesizerAgent. Merges findings → answer.
│
└── scrapers/
    ├── base_scraper.py         BaseScraper. Circuit breaker. Timeout.
    │                           Normalise output format.
    ├── registry.py             ScraperRegistry. Concurrent execution.
    │                           Isolates individual scraper failures.
    ├── hackernews.py           Algolia HN API. Distills queries to keywords.
    ├── reddit.py               PRAW. Auto-disables if no credentials.
    └── web.py                  DuckDuckGo Lite. No credentials needed.
```

---

## 5. Key Design Decisions

### Why Gemini is hardcoded as orchestrator
The orchestrator needs to reason about all available providers and produce a
plan. This requires the best available free model with the largest context
window. Gemini 2.0 Flash (1M token context, 1K RPD free) is the only model
that reliably does this well on the free tier. When Gemini is unavailable
(429), `_fallback_plan()` produces a valid plan without any LLM call using
heuristics from `agents.yaml` strengths tags.

### Why the key pool returns KeyState, not just the key string
When a provider returns 429, the caller needs to mark that specific key as in
cooldown — not just know that the call failed. `get_orchestrator_key()` returns
`(api_key_value, model, key_state)` so the orchestrator can call
`key_state.set_cooldown(delay)` with the exact retry delay from the error.

### Why scrapers use a circuit breaker
A scraper that fails repeatedly (network down, rate limited, HTML changed)
would slow every query by waiting for timeouts. After 3 consecutive failures
the circuit opens and the scraper is skipped entirely for 5 minutes. This
keeps query latency predictable.

### Why HackerNews distills queries to keywords
The Algolia API is a keyword search engine, not a semantic search. Sending
"give me all the information you can find on capacitors and transistors in
electronics" returns 0 results. Extracting ["capacitors", "transistors",
"electronics"] returns dozens. The scraper tries multi-keyword first (most
specific), then individual keywords as fallback.

### Why analysts return JSON contracts
Free-form text from analysts would require the synthesizer to parse prose from
potentially 4 different models. Structured JSON with `confidence`,
`key_findings`, `contradictions`, `needs_more_info` means the synthesizer
always has machine-readable input regardless of which models ran. Failed
JSON parses are wrapped as findings rather than discarded.

### Why everything is logged to SQLite
The thought chain (`thought_chain` table) records every pipeline step with
timestamps. This enables: `/chain <id>` in the CLI, future visualization,
debugging exactly which step produced a bad result, and building a query
cache (future feature) by comparing embeddings of past queries.

---

## 6. Configuration Reference

### `agents.yaml` — full annotated structure

```yaml
# The only hardcoded role in the system
orchestrator:
  provider: gemini          # always Gemini
  model: gemini-2.0-flash   # model string passed to the SDK
  keys: [GEMINI_KEY_1, GEMINI_KEY_2]  # env var names

providers:
  <provider_name>:
    base_url: "..."         # OpenAI-compatible endpoint (not used for gemini/cohere)
    rpm_limit: 30           # requests per minute — enforced by key pool
    daily_limit: 14400      # requests per day — enforced by key pool
    strengths:              # tags used by orchestrator for role assignment
      - speed               # good for triage (high volume, low latency)
      - reasoning           # good for complex analysis
      - analysis            # good for analyst role
      - synthesis           # good for final answer generation
      - rag                 # good for citation-aware synthesis
      - general             # fallback — can do anything
      - long_context        # can handle large chunks
    models:
      fast: "model-string"      # fastest/cheapest model for this provider
      capable: "model-string"   # best quality model
      default: "model-string"   # what to use when orchestrator doesn't specify
    keys:
      - ENV_VAR_NAME_1      # name of env var in .env — NOT the key itself
      - ENV_VAR_NAME_2      # add more as you create accounts

thresholds:
  relevance_min_score: 6    # 0-10, chunks below this are dropped in triage
  confidence_min: 0.70      # future: trigger second pass if below this
  max_chunk_tokens: 3000    # max tokens per chunk sent to analyst
  max_chunks: 20            # cap on total chunks processed per query

scrapers:
  hackernews:
    enabled: true
    results_per_query: 15   # how many HN posts to fetch
    timeout_seconds: 10     # abort if takes longer
  reddit:
    enabled: true
    results_per_query: 10
    timeout_seconds: 15
    subreddits: []          # empty = search all Reddit; ["python","rust"] = specific subs
  web:
    enabled: true
    results_per_query: 8
    timeout_seconds: 12
```

### `.env` — key format by provider

```env
# Gemini — starts with "AIza"
GEMINI_KEY_1=AIzaSy...

# Groq — starts with "gsk_"
GROQ_KEY_1=gsk_...

# OpenRouter — starts with "sk-or-"
OR_KEY_1=sk-or-...

# Cerebras — varies
CEREBRAS_KEY_1=csk-...

# Cohere — varies
COHERE_KEY_1=...

# GitHub — starts with "ghp_" or "github_pat_"
GH_KEY_1=ghp_...

# Reddit (optional)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=council_bot/1.0
```

---

## 7. Adding API Keys

**Step 1** — Add the env var name to `agents.yaml`:
```yaml
providers:
  groq:
    keys: [GROQ_KEY_1, GROQ_KEY_2, GROQ_KEY_3]  # ← add here
```

**Step 2** — Add the key value to `.env`:
```env
GROQ_KEY_3=gsk_your_new_key_here
```

**That's it.** No code changes. The key pool builds itself from yaml on startup.
The orchestrator's snapshot will show more `available_keys` for that provider,
and it will assign more work to it.

**Important:** Keys from the same provider account share one quota pool. To
genuinely multiply throughput you need keys from **different accounts** (different
email addresses). Keys 1 and 2 from the same Gemini account both count against
the same 1K RPD limit.

---

## 8. Adding a New Scraper

**Step 1** — Create `scrapers/my_scraper.py`:

```python
from scrapers.base_scraper import BaseScraper
import aiohttp

class MyScraper(BaseScraper):
    def __init__(self, config: dict):
        super().__init__("my_scraper", config)
        # read any extra config: self.api_key = os.getenv("MY_KEY", "")

    async def _fetch(self, query: str) -> list[dict]:
        # Do your fetching here. Raise on error — BaseScraper catches it.
        # Return list of dicts with at minimum: url and content keys.
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.example.com?q={query}") as r:
                data = await r.json()

        return [
            {
                "source": "my_scraper",
                "url": item["link"],
                "content": item["text"],
            }
            for item in data["results"]
        ]
```

**Step 2** — Register in `scrapers/registry.py`:
```python
from scrapers.my_scraper import MyScraper

scraper_classes = {
    "hackernews": HackerNewsScraper,
    "reddit":     RedditScraper,
    "web":        WebScraper,
    "my_scraper": MyScraper,          # ← add here
}
```

**Step 3** — Add config in `agents.yaml`:
```yaml
scrapers:
  my_scraper:
    enabled: true
    results_per_query: 10
    timeout_seconds: 10
```

The orchestrator will now be able to assign `"my_scraper"` in its plans. To
tell it when to use it, you can add it to `AVAILABLE_SCRAPERS` in
`agents/orchestrator.py`.

**Rules for `_fetch()`:**
- Must be `async`
- Raise any exception freely — `BaseScraper.scrape()` catches everything
- Never return None — return `[]` if no results
- The `source` field should be your scraper name
- Content should be plain text, max ~3000 chars per item (truncated later)

---

## 9. Adding a New LLM Provider

**Step 1** — Add to `agents.yaml`:
```yaml
providers:
  my_provider:
    base_url: "https://api.myprovider.com/v1"  # OpenAI-compatible endpoint
    rpm_limit: 25
    daily_limit: 500
    strengths: [analysis, general]
    models:
      default: "my-model-name"
    keys: [MY_PROVIDER_KEY_1]
```

**Step 2** — Add to `.env`:
```env
MY_PROVIDER_KEY_1=your_key_here
```

**Step 3** — Handle in `BaseAgent._call_provider()` if not OpenAI-compatible.

If your provider uses the OpenAI SDK format (most do), it already works — the
`_call_openai_compatible()` method in `base_agent.py` reads `base_url` from
the pool and sends a standard `chat.completions.create` call.

If your provider has a unique SDK (like Gemini or Cohere), add a branch:
```python
async def _call_provider(self, key: KeyState, prompt: str) -> str:
    if self.provider == "gemini":
        return await self._call_gemini(key.value, prompt)
    elif self.provider == "cohere":
        return await self._call_cohere(key.value, prompt)
    elif self.provider == "my_provider":
        return await self._call_my_provider(key.value, prompt)  # ← add
    else:
        return await self._call_openai_compatible(key.value, prompt)
```

---

## 10. Database Schema

The SQLite database (`council.db`) has 4 tables.

### `chunks`
One row per scraped chunk that passed triage.
```sql
id              INTEGER  PRIMARY KEY
query_id        TEXT     8-char query identifier
source          TEXT     "hackernews" | "reddit" | "web"
url             TEXT     original source URL
content         TEXT     scraped text (max 4000 chars)
relevance_score REAL     triage score 0.0-10.0
created_at      REAL     unix timestamp
```

### `agent_outputs`
One row per LLM call.
```sql
id              INTEGER  PRIMARY KEY
query_id        TEXT
agent_id        TEXT     "triage" | "analyst_0" | "synthesizer" etc.
provider        TEXT     "groq" | "openrouter" | "cohere" etc.
model           TEXT     exact model string used
input_tokens    INTEGER  (not yet populated — future)
output_tokens   INTEGER  (not yet populated — future)
latency_ms      REAL     wall clock time for the call
output_json     TEXT     first 2000 chars of what the agent returned
created_at      REAL
```

### `thought_chain`
Full step-by-step lineage for every query.
```sql
id              INTEGER  PRIMARY KEY
query_id        TEXT
step            TEXT     "start" | "orchestrator_plan" | "scraped" |
                         "triage" | "analyse_start" | "analysed" |
                         "done" | "orchestrator" (on error)
note            TEXT     human-readable detail (max 1000 chars)
created_at      REAL
```

Use `/chain <query_id>` in the CLI to read this for any query.

### `queries`
Final summary of each completed query.
```sql
id              INTEGER  PRIMARY KEY
query_id        TEXT     UNIQUE
query_text      TEXT     original user query
profile         TEXT     classification used
plan_json       TEXT     full orchestrator plan as JSON
answer          TEXT     final answer (max 8000 chars)
confidence      REAL     0.0-1.0
duration_ms     REAL     total wall time
created_at      REAL
```

---

## 11. Error Handling Philosophy

**The pipeline must never crash from a provider or scraper failure.**

Every stage follows the same pattern:
```python
try:
    result = await do_the_thing()
except Exception as e:
    logger.error(f"Stage X failed: {e}")
    result = safe_default_value
```

Specific rules by component:

| Component | On failure | Behaviour |
|---|---|---|
| Orchestrator (Gemini 429) | Mark key in cooldown | Use `_fallback_plan()` |
| Orchestrator (other error) | Record error on key | Use `_fallback_plan()` |
| Scraper (any error) | Increment circuit counter | Return `[]` |
| Scraper (3rd failure) | Open circuit for 5 min | Skip until recovery |
| Triage (all chunks drop) | Safety net | Keep top 3 chunks |
| Analyst (exception) | Log error | Drop that analyst's output |
| Analyst (bad JSON) | Wrap raw text | Keep as a finding |
| Synthesizer (fails) | Concatenate raw findings | Return with confidence 0.3 |
| State store (any) | Log only | Pipeline continues |

The `core/exceptions.py` defines the hierarchy but all exceptions are treated
as non-fatal at the pipeline level. The only fatal error is a missing or
invalid `agents.yaml` — the program cannot start without config.

---

## 12. Known Limitations and Workarounds

### Gemini daily quota exhausted quickly
**Problem:** Gemini free tier has only 1K RPD and the orchestrator uses ~800
tokens per query. With 2 keys from 2 accounts, that's ~2500 queries/day total.
**Workaround:** Create more Gemini accounts (different Gmail). The fallback
plan runs without Gemini, so the system stays functional even when all Gemini
keys are exhausted — just with simpler role assignments.

### HackerNews returns 0 for niche topics
**Problem:** Algolia keyword search. Topics with no HN discussion return
nothing regardless of how the query is phrased.
**Workaround:** The scraper tries individual keywords as fallback. If truly
no coverage exists, the pipeline continues with whatever other scrapers found.
Web scraper is more likely to find niche content.

### Reddit requires app registration
**Problem:** PRAW needs OAuth credentials.
**Workaround:** Reddit scraper auto-disables if credentials are missing. The
system works without Reddit. To enable: create a "script" app at
`reddit.com/prefs/apps`, get client_id and client_secret, add to `.env`.

### OpenRouter free models get rotated
**Problem:** Models with `:free` suffix may be removed or throttled without
notice.
**Workaround:** The orchestrator picks from whatever the snapshot shows as
available. If a model disappears, the key pool will show daily_remaining 0
(since calls fail) and the orchestrator switches providers. Update model
strings in `agents.yaml` when you see repeated failures from OpenRouter.

### Cohere 1K requests/month limit
**Problem:** Very low monthly cap on the trial tier.
**Workaround:** The orchestrator prioritises Cohere only for synthesis
(1 call per query). At 1 query per day average, this is sustainable. Create
more Cohere accounts to expand the pool. Alternatively, add the `synthesis`
strength to another provider in `agents.yaml`.

### No semantic dedup yet
**Problem:** The same information scraped from multiple sources is sent to
analysts multiple times, wasting tokens.
**Future fix:** Add `scrapers/dedup.py` using `sentence-transformers
all-MiniLM-L6-v2` (runs locally, no API needed). Insert between triage and
state_store in `pipeline.py`.

---

## 13. CLI Commands

```
council> <any text>       Run a research query
council> /status          Key pool quota and scraper circuit breaker status
council> /history         Last 10 queries with query_id, profile, confidence
council> /chain <id>      Full thought chain for a query (use id from /history)
council> /help            Command list
council> /quit            Exit
```

### Reading `/status`
```
── KEY POOL STATUS ─────────────────────────────────────────
  GROQ
    GROQ_KEY_1           ✓ ready           daily_remaining=14200
    GROQ_KEY_2           ✗ not ready       daily_remaining=0  cooldown=47s

── SCRAPER STATUS ──────────────────────────────────────────
  hackernews       ✓ available
  reddit           ✗ unavailable [disabled]
  web              ✓ available
```

`cooldown=47s` means the key was rate-limited and will be usable again in 47s.
`daily_remaining=0` means the key's daily quota is fully exhausted.
`[disabled]` on a scraper means `enabled: false` in yaml or no credentials.
`[circuit open]` means 3+ consecutive scraper failures — will auto-recover.

### Reading `/chain`
```
── THOUGHT CHAIN: 1fa0fe08 ───────────────────────────────
  [14:22:01] start                  query: give me all info on...
  [14:22:01] orchestrator           fallback: rate_limit
  [14:22:02] scrape_start           ['hackernews', 'web']
  [14:22:04] scraped                12 chunks
  [14:22:11] triage                 kept 7/12
  [14:22:11] analyse_start          2 analysts
  [14:22:18] analysed               2 outputs
  [14:22:24] done                   confidence=0.71 duration=23400ms
```

If `orchestrator` step shows `fallback: rate_limit`, Gemini was 429'd and the
system used its heuristic fallback plan. The rest of the pipeline still ran.

---

## 14. Debugging Guide

### "Orchestrator API call failed: 429"
Gemini quota exhausted. The system falls back automatically. To fix:
- Wait for quota reset (midnight Pacific time)
- Add more Gemini keys from different accounts
- Check `council.log` for the cooldown duration

### "0 chunks from hackernews"
The topic has no HN coverage, or the keyword distillation produced terms with
no matches. Check `council.log` for the distilled query terms. Try enabling
the web scraper.

### "All analysts failed to return results"
Usually a rate limit cascade — all providers exhausted simultaneously. Check
`/status` to see key states. Wait for cooldowns or add more keys.

### Analyst returns bad JSON
Check `council.log` for `[analyst_X] JSON parse failed, wrapping raw text`.
This is non-fatal — the raw text becomes a finding. If it happens consistently
for one provider, that provider's model may not follow JSON instructions well.
Try a different model in `agents.yaml` for that provider.

### Scraper circuit open
`[scraper_name] Circuit OPEN after 3 consecutive failures` in `council.log`.
The scraper will auto-recover after 5 minutes. To force immediate reset,
restart the program.

### "No providers available in snapshot"
All keys are either unconfigured (empty in `.env`) or in cooldown. Check
`/status` to see key states.

### Checking logs
```bash
# All errors and warnings from the last run
grep -E "ERROR|WARNING" council.log | tail -50

# Everything for a specific query
grep "1fa0fe08" council.log

# Orchestrator decisions
grep "orchestrator" council.log | tail -20
```

---

## 15. Extending the Pipeline

### Add a query cache
1. In `state_store.py`: add `get_cached_result(embedding)` and
   `save_to_cache(query, embedding, result)`
2. In `pipeline.py` before Stage 1: compute embedding with
   `sentence-transformers`, check cache with cosine similarity > 0.95
3. Return cached result immediately if hit

### Add a fact-checker
After Stage 5 in `pipeline.py`:
```python
fact_checker = FactCheckerAgent(pool, ...)
result = await fact_checker.verify(answer, sources)
# attaches verified/unverified flags to each claim
```
Implement in `agents/fact_checker.py` extending `BaseAgent`.

### Add a Gradio web UI
Replace `main.py`'s CLI loop with:
```python
import gradio as gr

def query_handler(text):
    result = asyncio.run(run(text, pool, registry))
    return result["answer"], result["confidence"], str(result["sources"])

gr.Interface(
    fn=query_handler,
    inputs=gr.Textbox(label="Query"),
    outputs=[gr.Textbox(label="Answer"), gr.Number(label="Confidence"), gr.Textbox(label="Sources")],
).launch()
```

### Add telemetry graphs
Query `agent_outputs` table and compute:
- Tokens used per provider per day
- Average latency per agent role
- Confidence distribution over time
- Most-used providers by the orchestrator

Use `pyvis` + `networkx` for pipeline flow graphs, `plotly` for time-series.

### Add academic scraper
Create `scrapers/academic.py` using the arXiv API (free, no auth):
```
https://export.arxiv.org/api/query?search_query=all:{query}&max_results=10
```
Returns XML — parse with `xml.etree.ElementTree`.

### Add semantic deduplication
After triage, before saving chunks:
```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")  # downloads once, runs local
embeddings = model.encode([c["content"] for c in scored])
# cosine similarity matrix, drop duplicates above 0.92 threshold
```
This runs locally with no API cost and can cut token usage 40-60% on popular
topics where multiple sources repeat the same information.
