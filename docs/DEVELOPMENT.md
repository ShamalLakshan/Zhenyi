# Development Guide

## Project Structure

```
zhenyi/
├── agents/              # LLM agents
├── core/                # Pipeline & orchestration
├── scrapers/            # Data collection
├── web-ui/              # React frontend
├── docs/                # Documentation
├── prompt-templates/    # LLM prompts
└── server.py            # FastAPI backend
```

## Development Setup

### Prerequisites
- Python 3.9+
- Node.js 18+ (for frontend)
- Git

### Installation

```bash
# 1. Clone and setup Python environment
git clone https://github.com/yourusername/zhenyi.git
cd zhenyi
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 4. Optional: Setup frontend
cd web-ui
npm install
cd ..
```

### Running Development Server

```bash
# Backend with auto-reload
uvicorn server:app --reload --host 0.0.0.0 --port 8000

# Frontend (in separate terminal)
cd web-ui
npm run dev
```

## Architecture Overview

### Core Components

**Pipeline** (`core/pipeline.py`)
- Orchestrates 5-stage execution
- Manages event emission
- Handles error recovery
- Returns structured results

**Key Pool** (`core/key_pool.py`)
- Tracks API key availability
- Selects optimal provider per role
- Implements fallback strategy
- Monitors daily quotas

**State Store** (`core/state_store.py`)
- SQLite persistence layer
- Stores queries and history
- Manages thought chains
- Supports concurrent access

**Event Bus** (`core/events.py`)
- Publishes pipeline events
- WebSocket subscriptions
- Real-time frontend updates

### Agent System

**Base Agent** (`agents/base_agent.py`)
- Common interface for all LLMs
- Provider-agnostic call handling
- Error recovery with retries
- Token usage tracking

**Orchestrator** (`agents/orchestrator.py`)
- Gemini-specific implementation
- Query intent detection
- Scraper selection logic
- Plan generation

**Triage** (`agents/triage.py`)
- Chunk relevance scoring
- Multiple scoring modes
- Configurable thresholds

**Analyst** (`agents/analyst.py`)
- Content analysis
- Finding extraction
- Reasoning chain capture

**Synthesizer** (`agents/synthesizer.py`)
- Answer compilation
- Citation management
- Confidence calculation

### Scraper System

**Base Scraper** (`scrapers/base_scraper.py`)
- Circuit breaker pattern
- Retry logic
- Rate limiting
- Timeout handling

**Registry** (`scrapers/registry.py`)
- Parallel execution
- Result aggregation
- Error handling

## Adding Features

### 1. Adding a New Scraper

Create `scrapers/my_scraper.py`:

```python
from scrapers.base_scraper import BaseScraper
import logging

logger = logging.getLogger(__name__)

class MyScraperScraper(BaseScraper):
    def __init__(self):
        super().__init__("my_scraper")
    
    async def scrape(self, query: str) -> list[dict]:
        """
        Scrape data for query.
        
        Returns:
            List of chunks with: content, source, title, url
        """
        try:
            # Your scraping logic
            results = []
            # ... fetch and parse data ...
            results.append({
                "content": "...",
                "source": "my_scraper",
                "title": "...",
                "url": "https://..."
            })
            return results
        except Exception as e:
            logger.error(f"[my_scraper] Error: {e}")
            return []
```

Register in `scrapers/registry.py`:

```python
from scrapers.my_scraper import MyScraperScraper

# In SCRAPER_MAP
"my_scraper": MyScraperScraper()
```

Add to `agents.yaml`:

```yaml
scrapers:
  my_scraper:
    enabled: true
    rate_limit: 100
    timeout: 15
```

### 2. Adding a New LLM Provider

Edit `core/key_pool.py` to support new provider:

```python
class KeyPool:
    async def call_provider(self, provider: str, model: str, prompt: str, **kwargs):
        if provider == "myprovider":
            return await self._call_myprovider(model, prompt, **kwargs)
        # ... existing providers ...
    
    async def _call_myprovider(self, model: str, prompt: str, **kwargs):
        # Implementation using provider's API
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.myprovider.com/v1/chat",
                json={"model": model, "prompt": prompt}
            )
            return response.json()["text"]
```

Add configuration to `agents.yaml`:

```yaml
providers:
  myprovider:
    keys: [MYPROVIDER_KEY_1]
    rpm_limit: 30
    daily_limit: 10000
    strengths: [analysis, reasoning]
    models:
      default: "best-model"
```

### 3. Adding a New Agent Role

Create `agents/my_role.py`:

```python
from agents.base_agent import BaseAgent

class MyRoleAgent(BaseAgent):
    def __init__(self, role_name: str, pool: KeyPool, provider: str, model: str):
        super().__init__(role_name, pool, provider=provider, model=model)
    
    async def execute(self, input_data: dict, query_id: str = "") -> dict:
        """Execute the role."""
        prompt = self._build_prompt(input_data)
        result = await self.call(prompt, query_id=query_id)
        return self._parse_result(result)
```

Update orchestrator prompt in `agents/orchestrator.py` to assign the new role.

### 4. Extending the Frontend

Frontend is in React + Vite in `web-ui/`.

Key components:
- `App.tsx` - Main component
- `components/` - Reusable components
- `lib/` - Utility functions

For UI updates:
```bash
cd web-ui
npm run dev  # Start dev server with HMR
```

## Testing

### Unit Tests

```bash
# Run pytest
pytest tests/

# With coverage
pytest --cov=. tests/
```

### Integration Tests

```bash
# Test full pipeline
python -m pytest tests/test_integration.py -v

# Test specific stage
python -m pytest tests/test_pipeline.py::test_orchestrator -v
```

### Manual Testing

```bash
# Start server
uvicorn server:app --reload

# In another terminal, test endpoint
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test query"}'

# Monitor WebSocket
wscat -c ws://localhost:8000/ws/query/{query_id}
```

## Code Style

- Python: Follow PEP 8 with `black` formatter
- TypeScript: ESLint configuration in `web-ui/`
- Commit: Use conventional commits (feat:, fix:, docs:, etc.)

### Format Code

```bash
# Python
black .

# TypeScript
cd web-ui
npm run lint --fix
```

## Performance Tips

1. **Reduce Scraper Count**: Fewer scrapers = faster execution
2. **Use scraper_only Triage**: Skip LLM scoring for speed
3. **Batch Requests**: Reuse connections
4. **Cache Results**: Avoid re-querying same questions

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Execution Logs

```bash
# View query logs
ls logs/queries/

# Specific query
cat logs/queries/{query_id}/orchestrator_plan.json

# Agent reasoning
cat logs/queries/{query_id}/agent_reasoning/
```

### Monitor Provider Status

```bash
# Check key availability
curl http://localhost:8000/api/status

# Query database directly
sqlite3 zhenyi.db
> SELECT * FROM queries LIMIT 5;
```

## Common Issues

### Issue: All providers exhausted

**Cause**: Daily quotas exceeded  
**Solution**: 
- Add more API keys to agents.yaml
- Wait for quota reset (usually UTC midnight)
- Use different providers

### Issue: Scraper timeouts

**Cause**: Website slow or blocked  
**Solution**:
- Increase timeout in agents.yaml
- Disable problematic scraper
- Add backoff/retry logic

### Issue: LLM model not found

**Cause**: Model name changed or deprecated  
**Solution**:
- Check provider docs for current models
- Update agents.yaml with correct model name
- Test model availability via provider console

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/my-feature`
3. Make changes and test
4. Commit: `git commit -m "feat: description"`
5. Push: `git push origin feature/my-feature`
6. Open pull request

## Security Considerations

- Never commit `.env` file
- Redact API keys in logs (handled automatically)
- Use environment variables for secrets
- Validate user input in endpoints
- Implement authentication for production

For production deployment:
- Use HTTPS/TLS
- Add authentication/authorization
- Implement rate limiting
- Set up monitoring/alerting
- Use environment-specific configs

## Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [Architecture Overview](ARCHITECTURE.md)
- [Setup Guide](SETUP.md)
- [API Reference](API.md)
