# Contributing to Zhenyi

Thank you for your interest in contributing to Zhenyi! Zhenyi is an open-source, multi-agent autonomous research studio designed to operate effectively using free-tier LLM providers, intelligent scraper pipelines, and transparent reasoning graphs.

---

## Table of Contents

1. [Project Directory Layout](#1-project-directory-layout)
2. [Development Setup](#2-development-setup)
   - [Prerequisites](#prerequisites)
   - [Backend Setup (Python)](#backend-setup-python)
   - [Frontend Setup (React + Vite)](#frontend-setup-react--vite)
   - [Environment Variables (.env)](#environment-variables-env)
3. [Running the Application](#3-running-the-application)
   - [Development Mode](#development-mode)
   - [Production Build](#production-build)
4. [Adding a New Scraper](#4-adding-a-new-scraper)
5. [Adding a New LLM Provider](#5-adding-a-new-llm-provider)
6. [Database Schema (SQLite)](#6-database-schema-sqlite)
7. [Error Handling & Circuit Breakers](#7-error-handling--circuit-breakers)
8. [Coding Standards & Verification](#8-coding-standards--verification)
9. [Submitting a Pull Request](#9-submitting-a-pull-request)

---

## 1. Project Directory Layout

```
Zhenyi/
├── agents/                 # LLM Agent implementations (orchestrator, triage, analyst, synthesizer)
├── core/                   # Core orchestrator, pipeline stages, key pool scheduler, event bus
├── scrapers/               # Built-in scraper implementations and registry
├── web-ui/                 # React + TypeScript + Tailwind + Force Graph frontend
│   ├── src/                # UI components, state stores, knowledge graph rendering
│   ├── public/             # Static assets (logo, favicon)
│   └── dist/               # Compiled frontend production bundle served by FastAPI
├── diagrams/               # Architecture diagrams and system flowcharts
├── server.py               # FastAPI backend & WebSocket server
├── agents.yaml             # Agent models, provider capabilities, rate limits, and scraper settings
├── requirements.txt        # Python package dependencies
├── pyproject.toml          # Project metadata and tool configuration
├── API.md                  # REST and WebSocket API specification
├── ARCHITECTURE.md         # Deep-dive architecture and lifecycle explanation
├── CONTRIBUTING.md         # Developer setup and contribution guide (this document)
├── SECURITY.md             # Security policy and disclosure guide
└── LICENSE                 # Apache 2.0 open-source license
```

---

## 2. Development Setup

### Container Development (Recommended)

To avoid local Python and Node dependency issues, you can develop directly inside an isolated container using **Podman** or **Docker**:

1. **Using VS Code / Cursor / Windsurf Dev Containers**:
   - Open the project in VS Code with the *Dev Containers* extension installed.
   - Click **"Reopen in Container"** when prompted. The IDE will mount your workspace into the container with hot-reload and language tools enabled.

2. **Using the CLI Helper**:
   ```bash
   cp .env.example .env
   # Start dev container with live code reload
   ./scripts/container.sh dev
   ```

3. **Disk Hygiene**:
   To reclaim container storage at any time:
   ```bash
   ./scripts/container.sh clean
   ```

---

### Native Local Setup (Without Containers)

#### Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18.0.0 or higher
- **npm** or **pnpm**
- **Git**
- Free-tier API keys for at least one supported LLM provider (Google Gemini recommended as orchestrator)

#### Backend Setup (Python)

Clone the repository and create an isolated virtual environment:

```bash
git clone https://github.com/ShamalLakshan/zhenyi.git
cd zhenyi

# Using standard venv
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Or using uv (recommended for speed)
uv venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Frontend Setup (React + Vite)

In a separate terminal (or navigating into `web-ui`):

```bash
cd web-ui
npm install
cd ..
```

### Environment Variables (.env)

Copy the sample environment file to `.env`:

```bash
cp .env.example .env
```

Populate the `.env` file with your keys. Zhenyi can run with as few as one provider (e.g. Gemini), but performs best when multiple free-tier providers are configured:

```env
# Google Gemini (Default Orchestrator & Research Analysis)
GEMINI_KEY_1=AIzaSy...

# Groq (Ultra-fast Triage and Reasoning)
GROQ_KEY_1=gsk_...

# OpenRouter (General Synthesis & Deep Reasoning)
OR_KEY_1=sk-or-...

# Cerebras (High-speed inference)
CEREBRAS_KEY_1=csk-...

# Cohere (Synthesis and Structured Findings)
COHERE_KEY_1=...

# GitHub Models (Alternative fast inference)
GITHUB_TOKEN=ghp_...
```

> [!NOTE]
> All keys in `agents.yaml` map to the *variable names* in `.env`. Actual secret tokens are kept exclusively in `.env` and are strictly excluded from version control via `.gitignore`.

---

## 3. Running the Application

### Development Mode

Run the FastAPI backend with hot reloading:

```bash
# Terminal 1: Backend
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Run the Vite dev server for the frontend (with instant hot module replacement):

```bash
# Terminal 2: Frontend
cd web-ui
npm run dev
```

The Vite dev server proxies API and WebSocket requests to `http://localhost:8000`.

### Production Build

FastAPI serves the static frontend directly from `web-ui/dist/`. To build and run in production mode:

```bash
# 1. Build the frontend bundle
cd web-ui
npm run build
cd ..

# 2. Run backend
uvicorn server:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` in your browser.

---

## 4. Adding a New Scraper

Zhenyi features a pluggable scraping architecture. All scrapers inherit from `BaseScraper` in `scrapers/base_scraper.py`.

### Step 1: Create the Scraper Module

Create `scrapers/my_scraper.py`:

```python
import aiohttp
from scrapers.base_scraper import BaseScraper

class MyCustomScraper(BaseScraper):
    def __init__(self, config: dict):
        super().__init__("my_scraper", config)
        # Read scraper-specific settings
        self.endpoint = config.get("endpoint", "https://api.example.com/search")

    async def _fetch(self, query: str) -> list[dict]:
        """Fetch raw data and return a list of standard chunk dicts."""
        async with aiohttp.ClientSession() as session:
            params = {"q": query}
            async with session.get(self.endpoint, params=params, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        results = []
        for item in data.get("items", []):
            results.append({
                "source": self.name,
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "content": item.get("body", "")[:3000],  # Keep raw text within bounds
            })
        return results
```

### Step 2: Register in Scraper Registry

In `scrapers/registry.py`:

```python
from scrapers.my_scraper import MyCustomScraper

scraper_classes = {
    "hackernews": HackerNewsScraper,
    "web": WebScraper,
    "arxiv": ArxivScraper,
    "my_scraper": MyCustomScraper,  # <-- Register here
}
```

### Step 3: Configure in `agents.yaml`

```yaml
scrapers:
  my_scraper:
    enabled: true
    results_per_query: 10
    timeout_seconds: 12
```

### Scraper Rules:
- Must be asynchronous (`async def _fetch`).
- Never raise unhandled fatal errors; raise standard exceptions freely, as `BaseScraper.scrape()` automatically catches them and triggers the circuit breaker if failures persist.
- Return an empty list `[]` if no results are found.

---

## 5. Adding a New LLM Provider

Zhenyi abstracts LLM providers through `core/key_pool.py` and `agents/base_agent.py`.

### Step 1: Add Provider to `agents.yaml`

```yaml
providers:
  my_new_provider:
    base_url: "https://api.mynewprovider.com/v1"
    rpm_limit: 30
    daily_limit: 1000
    strengths: [analysis, general]
    models:
      default: "provider-model-id"
      fast: "provider-model-fast"
    keys:
      - MY_NEW_PROVIDER_KEY_1
```

### Step 2: Add Secret to `.env`

```env
MY_NEW_PROVIDER_KEY_1=your_secret_key_here
```

### Step 3: Handle in `BaseAgent` (if Non-OpenAI Compatible)

If the provider uses the standard OpenAI API specification, **no code change is needed**—`BaseAgent._call_openai_compatible()` handles it automatically.

If the provider requires a custom SDK or client protocol, add a handler branch in `agents/base_agent.py`:

```python
async def _call_provider(self, key: KeyState, prompt: str) -> str:
    if self.provider == "gemini":
        return await self._call_gemini(key.value, prompt)
    elif self.provider == "cohere":
        return await self._call_cohere(key.value, prompt)
    elif self.provider == "my_new_provider":
        return await self._call_custom_provider(key.value, prompt)
    else:
        return await self._call_openai_compatible(key.value, prompt)
```

---

## 6. Database Schema (SQLite)

Zhenyi stores query telemetry and graph data locally in `zhenyi.db`.

| Table | Description |
|---|---|
| `chunks` | Scraped and triaged text chunks with relevance scores (0-10) and source URLs. |
| `agent_outputs` | Execution latency, models, providers, and raw output JSON for every agent invocation. |
| `thought_chain` | Ordered audit steps (`start`, `orchestrator_plan`, `scraped`, `triage`, `analysed`, `done`). |
| `queries` | User queries, assigned profiles, final answers, confidence scores, and execution durations. |

---

## 7. Error Handling & Circuit Breakers

The pipeline is built around graceful degradation:

- **Orchestrator 429 / Quota Error**: The key is placed in temporary cooldown and the pipeline automatically switches to a deterministic heuristic fallback plan (`_fallback_plan()`).
- **Scraper Errors**: Scraper failures are isolated. A circuit breaker pattern trips after 3 consecutive errors, temporarily disabling that source for 5 minutes without interrupting the rest of the research run.
- **Triage Failure**: If all chunks drop below the score threshold, a fallback safety mechanism retains the top 3 chunks to prevent total analysis starvation.
- **Analyst JSON Malformation**: If an LLM returns unstructured text rather than formatted JSON, the raw output is safely wrapped and preserved as a research finding.
- **Synthesizer Failure**: If final synthesis fails, raw analyst findings are concatenated and presented with an adjusted confidence score.

---

## 8. Coding Standards & Verification

- **Python**: PEP 8 style, clean typing annotations, asynchronous I/O (`asyncio`, `aiohttp`, `aiosqlite`).
- **TypeScript & React**: Modern functional components, strict typing, Tailwind CSS utility classes.
- **Linting & Typecheck**:
  ```bash
  # Frontend validation
  cd web-ui
  npm run lint
  npm run build
  cd ..
  ```
- **Local Testing**:
  Always verify that the server launches cleanly and that submitting a test query executes through the 5 pipeline stages.

---

## 9. Submitting a Pull Request

1. **Fork** the repository and create a descriptive branch:
   ```bash
   git checkout -b feature/awesome-scraper
   ```
2. **Commit** your changes with clear, imperative commit messages:
   ```bash
   git commit -m "Add OpenAlex academic scraper plugin"
   ```
3. **Verify Git Index**: Ensure no keys, database files (`zhenyi.db`), or temporary test artifacts are staged:
   ```bash
   git status
   ```
4. **Push** to your fork:
   ```bash
   git push origin feature/awesome-scraper
   ```
5. **Open a Pull Request** against `main` on GitHub with:
   - A clear description of the new feature or bug fix.
   - Any added `agents.yaml` or `.env.example` configurations.
   - Screenshots or terminal logs demonstrating successful execution.
