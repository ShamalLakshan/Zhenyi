# Setup and Installation

## Prerequisites

- Python 3.9+
- pip (Python package manager)
- Git (for cloning)
- Valid API keys for at least one LLM provider

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/zhenyi.git
cd zhenyi
```

### 2. Create Virtual Environment

**Windows**:
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux**:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### Setting API Keys

1. Copy the template:
```bash
cp .env.example .env
```

2. Edit `.env` and add your API keys:

```env
GEMINI_KEY_1=your_gemini_api_key
GROQ_KEY_1=your_groq_api_key
OR_KEY_1=your_openrouter_api_key
CEREBRAS_KEY_1=your_cerebras_api_key
COHERE_KEY_1=your_cohere_api_key
GITHUB_TOKEN=your_github_token
```

### Getting Free API Keys

Zhenyi is configured to work with free-tier LLM services. No payment required to get started.

**Google Gemini** (Orchestrator)
- Visit: https://ai.google.dev/
- Click "Get API Key"
- Instant free key generation
- Quota: 1,000 requests/day

**Groq** (Fast triage/analysis)
- Visit: https://console.groq.com/
- Sign up free
- Generate API key from dashboard
- Quota: 14,400 requests/day

**OpenRouter** (Reasoning/synthesis)
- Visit: https://openrouter.ai/
- Sign up free
- Create API key in settings
- Quota: 200 requests/day

**Cerebras** (High-speed analysis)
- Visit: https://cloud.cerebras.ai/
- Sign up free
- Generate API key
- Quota: 14,400 requests/day

**Cohere** (Synthesis/RAG)
- Visit: https://dashboard.cohere.com/
- Sign up free
- Create API key
- Quota: 1,000 requests/day

**GitHub Models** (General purpose)
- Visit: https://github.com/models
- Use GitHub account (requires existing account)
- Generate Personal Access Token
- Quota: 150 requests/day

### Configuration File (agents.yaml)

The `agents.yaml` file defines available providers and scrapers. Edit to customize:

```yaml
providers:
  gemini:
    keys: [GEMINI_KEY_1, GEMINI_KEY_2]
    rpm_limit: 15
    daily_limit: 1000
    strengths:
      - orchestration
      - planning
    models:
      default: gemini-2.5-flash

  groq:
    keys: [GROQ_KEY_1]
    rpm_limit: 30
    daily_limit: 14400
    strengths:
      - speed
      - triage
    models:
      default: llama-3.1-8b-instant
      capable: llama-3.3-70b-versatile

  openrouter:
    keys: [OR_KEY_1]
    rpm_limit: 20
    daily_limit: 200
    strengths:
      - reasoning
      - synthesis
    models:
      default: meta-llama/llama-3.3-70b-instruct

  cerebras:
    keys: [CEREBRAS_KEY_1]
    rpm_limit: 30
    daily_limit: 14400
    strengths:
      - speed
      - analysis
    models:
      default: llama3.1-8b

  cohere:
    keys: [COHERE_KEY_1]
    rpm_limit: 20
    daily_limit: 1000
    strengths:
      - synthesis
      - summarization
    models:
      default: command-a-03-2025

scrapers:
  hackernews:
    enabled: true
    rate_limit: 100
    timeout: 15
  
  arxiv:
    enabled: true
    rate_limit: 100
    timeout: 15
  
  web:
    enabled: true
    rate_limit: 50
    timeout: 20
```

**Key fields**:
- `keys`: List of environment variable names containing API keys
- `rate_limit`: Maximum requests per minute
- `timeout`: Request timeout in seconds
- `strengths`: Provider capabilities (orchestration, reasoning, speed, synthesis, etc.)
- `models`: Available models and fallbacks

### Enabling/Disabling Scrapers

Edit the `scrapers:` section in `agents.yaml`:

```yaml
scrapers:
  hackernews:
    enabled: true    # Enable this scraper
  
  arxiv:
    enabled: false   # Disable ArXiv scraper
```

## Running the Application

### CLI Mode (Python)

Interactive command-line interface:

```bash
python server.py
```

Then open browser to: http://localhost:8000

### Development Server

With auto-reload on code changes:

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

With Gunicorn (recommended for production):

```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker server:app --bind 0.0.0.0:8000
```

## Frontend Setup (Optional)

The web UI is optional. To build and develop the frontend:

### Install Dependencies
```bash
cd web-ui
npm install
```

### Development Mode
```bash
npm run dev
```

### Production Build
```bash
npm run build
```

### Run Built Frontend
```bash
npm run preview
```

The frontend will be served at `http://localhost:5173` in dev mode.

## Database Setup

The system automatically initializes SQLite database on first run. To reset:

```bash
# Backup existing database
cp zhenyi.db zhenyi.db.backup

# Delete to start fresh
rm zhenyi.db

# Database will auto-initialize on next run
```

## Troubleshooting

### Issue: "API key not found" error

**Solution**: Verify in `.env`:
- Key name matches configuration in `agents.yaml`
- Environment variable is exported
- API key format is valid for provider

```bash
# Verify env var is set (Windows)
echo %GEMINI_KEY_1%

# Verify env var is set (macOS/Linux)
echo $GEMINI_KEY_1
```

### Issue: All providers exhausted

**Solution**: Add more API keys or wait for quota reset

Check current status:
```bash
# Via API
curl http://localhost:8000/api/status

# Check key pool in code
python -c "from core.key_pool import KeyPool; pool = KeyPool(); print(pool.get_capabilities_snapshot())"
```

### Issue: Scraper timeouts

**Solution**: Increase timeout in `agents.yaml` or disable problematic scraper

```yaml
scrapers:
  arxiv:
    timeout: 30  # Increase from 15 to 30 seconds
```

### Issue: Port 8000 already in use

**Solution**: Use different port:
```bash
uvicorn server:app --port 8001
```

### Issue: Frontend not connecting to backend

**Solution**: Ensure backend is running and check CORS settings:
- Backend must be running on same host or CORS must be configured
- Frontend makes requests to `/api/` endpoints

## Environment Variables

All configuration can be set via environment variables. Full reference:

```env
# LLM Provider Keys (Free Tier)
GEMINI_KEY_1=...
GROQ_KEY_1=...
OR_KEY_1=...
CEREBRAS_KEY_1=...
COHERE_KEY_1=...
GITHUB_TOKEN=...

# Optional Settings
DATABASE_PATH=zhenyi.db
LOG_LEVEL=INFO
API_PORT=8000
API_HOST=0.0.0.0
```

## Performance Tuning

### For Limited Bandwidth

Edit `agents.yaml`:
```yaml
scrapers:
  youtube:
    enabled: false  # YouTube can use significant bandwidth
  
  arxiv:
    timeout: 5     # Reduce timeout
```

### For Limited API Quota

Use fewer/faster models:
```yaml
providers:
  groq:
    models:
      default: llama-3.1-8b-instant  # Faster, lighter
```

### For Fast Responses

Enable scraper_only triage mode:
```yaml
# In orchestrator prompt
triage_mode: scraper_only  # Skip LLM scoring
```

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design details
- Read [DEVELOPMENT.md](DEVELOPMENT.md) to extend the system
- Read [API.md](API.md) for endpoint documentation
