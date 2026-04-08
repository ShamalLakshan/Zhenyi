# LLM Research Council

Multi-provider research agent that uses free-tier LLM APIs.
Gemini acts as the orchestrator and dynamically assigns roles to other
providers based on the query and live key availability.

## Quick Start

```bash
# 1. Create and activate virtual environment (Windows)
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up API keys
copy .env.example .env
# Open .env and fill in your keys

# 4. Run
python main.py
```

## Commands

| Command | Description |
|---|---|
| `<any text>` | Run a research query |
| `/status` | Show key pool and scraper status |
| `/history` | Show last 10 queries |
| `/chain <id>` | Show thought chain for a query ID |
| `/help` | Show commands |
| `/quit` | Exit |

## Project Structure

```
council/
├── main.py                 # Entry point + CLI
├── agents.yaml             # Provider config and key references
├── .env                    # API keys (never commit this)
├── .env.example            # Template for .env
├── requirements.txt
│
├── core/
│   ├── key_pool.py         # Key state tracking + provider selection
│   ├── state_store.py      # SQLite: chunks, agent outputs, thought chain
│   ├── pipeline.py         # Pipeline orchestration
│   └── exceptions.py       # Custom exceptions
│
├── agents/
│   ├── base_agent.py       # LLM call handler (all providers)
│   ├── orchestrator.py     # Gemini planner — assigns roles dynamically
│   ├── triage.py           # Relevance scoring
│   ├── analyst.py          # Content analysis
│   └── synthesizer.py      # Final answer generation
│
└── scrapers/
    ├── base_scraper.py     # Circuit breaker + normalisation
    ├── registry.py         # Runs scrapers concurrently
    ├── hackernews.py       # No credentials required
    ├── reddit.py           # Requires REDDIT_CLIENT_ID/SECRET in .env
    └── web.py              # DuckDuckGo Lite — no credentials
```

## Adding More API Keys

Edit `agents.yaml` — add the env var name to the provider's `keys` list:

```yaml
providers:
  groq:
    keys: [GROQ_KEY_1, GROQ_KEY_2, GROQ_KEY_3]  # add here
```

Add the actual key value to `.env`:

```env
GROQ_KEY_3=gsk_your_new_key_here
```

No code changes needed.

## Adding a New Scraper

1. Create `scrapers/my_scraper.py` extending `BaseScraper`
2. Register it in `scrapers/registry.py` under `scraper_classes`
3. Add config in `agents.yaml` under `scrapers:`

## Logs

All pipeline activity is logged to `council.log`.
The SQLite database `council.db` stores all query history and thought chains.
Use `/chain <id>` in the CLI to trace any query step by step.
