# API Documentation

## Overview

Zhenyi provides a REST API for submitting research queries and retrieving results. Communication uses HTTP with WebSocket support for real-time progress updates.

Base URL: `http://localhost:8000/api`

## Endpoints

### Query Management

#### POST /query

Submit a new research query.

**Request**:
```json
{
  "query": "What are the latest developments in quantum computing?",
  "profile": "deep_research"  // Optional: simple_factual, current_factual, research, deep_research
}
```

**Response** (202 Accepted):
```json
{
  "query_id": "5c4f15d1",
  "status": "queued"
}
```

**WebSocket** (ws://localhost:8000/ws/query/{query_id}):
Subscribe to receive real-time pipeline events.

**Events**:
```json
{
  "type": "ORCHESTRATOR_DONE",
  "query_id": "5c4f15d1",
  "data": {
    "profile": "deep_research",
    "scrapers": ["web", "arxiv", "hackernews"],
    "reasoning": "Query requires multi-source research..."
  }
}
```

#### GET /query/{query_id}

Retrieve a specific query result.

**Response** (200):
```json
{
  "query_id": "5c4f15d1",
  "query": "What are the latest developments in quantum computing?",
  "profile": "deep_research",
  "status": "complete",
  "answer": "Recent quantum computing developments include...",
  "confidence": 0.87,
  "sources": [
    "https://arxiv.org/...",
    "https://news.ycombinator.com/..."
  ],
  "duration_ms": 42500,
  "created_at": "2026-04-23T14:25:00Z"
}
```

**Error** (404):
```json
{
  "error": "Query not found"
}
```

#### GET /history

Retrieve recent queries.

**Query Parameters**:
- `limit` (int, default: 50) - Number of queries to return
- `offset` (int, default: 0) - Pagination offset

**Response** (200):
```json
[
  {
    "query_id": "5c4f15d1",
    "query": "What are the latest developments in quantum computing?",
    "status": "complete",
    "created_at": "2026-04-23T14:25:00Z"
  },
  {
    "query_id": "5c4f15d2",
    "query": "History of artificial intelligence",
    "status": "complete",
    "created_at": "2026-04-23T13:50:00Z"
  }
]
```

#### DELETE /query/{query_id}

Delete a query and its history.

**Response** (200):
```json
{
  "message": "Query deleted"
}
```

### System Status

#### GET /status

Get current system status and provider information.

**Response** (200):
```json
{
  "status": "ready",
  "providers": {
    "gemini": {
      "available": true,
      "daily_remaining": 987,
      "daily_limit": 1000,
      "models": ["gemini-2.5-flash"]
    },
    "groq": {
      "available": true,
      "daily_remaining": 14200,
      "daily_limit": 14400,
      "models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
    }
  },
  "scrapers": {
    "hackernews": {"available": true, "status": "operational"},
    "arxiv": {"available": true, "status": "operational"},
    "web": {"available": true, "status": "operational"},
    "wikipedia": {"available": true, "status": "operational"}
  },
  "database": "connected",
  "uptime_seconds": 3600
}
```

#### GET /health

Health check endpoint for monitoring.

**Response** (200):
```json
{
  "status": "healthy",
  "timestamp": "2026-04-23T14:25:00Z"
}
```

### Debug Endpoints

#### GET /debug/query/{query_id}

Retrieve detailed execution trace for a query.

**Response** (200):
```json
{
  "query_id": "5c4f15d1",
  "query": "What are the latest developments in quantum computing?",
  "stages": {
    "orchestrator": {
      "status": "complete",
      "duration_ms": 2500,
      "plan": {
        "profile": "deep_research",
        "scrapers": ["web", "arxiv"],
        "analyst_count": 2
      }
    },
    "scraping": {
      "status": "complete",
      "duration_ms": 8000,
      "chunks_collected": 15
    },
    "triage": {
      "status": "complete",
      "duration_ms": 3000,
      "chunks_filtered": 15,
      "threshold": 6
    },
    "analysis": {
      "status": "complete",
      "duration_ms": 18000,
      "analysts_used": 2
    },
    "synthesis": {
      "status": "complete",
      "duration_ms": 2000
    }
  },
  "total_duration_ms": 33500,
  "api_calls": {
    "gemini": 1,
    "groq": 4,
    "total_tokens": 12500
  },
  "scrapers": {
    "web": 5,
    "arxiv": 3
  }
}
```

#### GET /debug/logs/{query_id}

Retrieve raw logs for a query (if available).

**Response** (200):
Stream of log entries as newline-delimited JSON

**Error** (404):
```json
{
  "error": "Logs not found for query"
}
```

## WebSocket Events

Connect to `ws://localhost:8000/ws/query/{query_id}` to receive real-time updates.

### Event Types

**QUERY_STARTED**
```json
{
  "type": "QUERY_STARTED",
  "query_id": "5c4f15d1",
  "data": {"query": "..."}
}
```

**ORCHESTRATOR_DONE**
```json
{
  "type": "ORCHESTRATOR_DONE",
  "query_id": "5c4f15d1",
  "data": {
    "profile": "deep_research",
    "scrapers": ["web", "arxiv"],
    "reasoning": "Query requires..."
  }
}
```

**SCRAPER_STARTED**
```json
{
  "type": "SCRAPER_STARTED",
  "query_id": "5c4f15d1",
  "data": {"scrapers": ["web", "arxiv"]}
}
```

**CHUNKS_COLLECTED**
```json
{
  "type": "CHUNKS_COLLECTED",
  "query_id": "5c4f15d1",
  "data": {
    "total_chunks": 15,
    "chunks": [
      {
        "source": "hackernews",
        "title": "...",
        "url": "https://..."
      }
    ]
  }
}
```

**CHUNKS_SCORED**
```json
{
  "type": "CHUNKS_SCORED",
  "query_id": "5c4f15d1",
  "data": {
    "scored_chunks": 15,
    "threshold": 6
  }
}
```

**ANALYST_DONE**
```json
{
  "type": "ANALYST_DONE",
  "query_id": "5c4f15d1",
  "data": {
    "successful_analysts": 2,
    "total_analysts": 2
  }
}
```

**QUERY_DONE**
```json
{
  "type": "QUERY_DONE",
  "query_id": "5c4f15d1",
  "data": {
    "status": "complete",
    "duration_ms": 33500,
    "answer_length": 2500
  }
}
```

## Error Responses

All error responses follow this format:

```json
{
  "error": "Error message",
  "status": 400,
  "query_id": "5c4f15d1"  // If applicable
}
```

### HTTP Status Codes

- `200 OK` - Successful request
- `202 Accepted` - Query submitted for processing
- `400 Bad Request` - Invalid request format
- `404 Not Found` - Query/resource not found
- `429 Too Many Requests` - Rate limited
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - All providers exhausted

## Rate Limiting

Global rate limits apply:
- 100 queries per minute
- 1000 queries per day

Rate limit status returned in response headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1681234560
```

## Authentication

Currently, Zhenyi has no authentication layer. Running on localhost only.

For production deployment with authentication, see [DEVELOPMENT.md](DEVELOPMENT.md#authentication).

## Examples

### Example 1: Simple Query

```bash
# Submit query
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is quantum computing?"}'

# Response
{"query_id": "5c4f15d1", "status": "queued"}

# Retrieve result (polling)
curl http://localhost:8000/api/query/5c4f15d1

# When ready, response includes answer
```

### Example 2: Real-time Progress (WebSocket)

```bash
# Using wscat or similar tool
wscat -c ws://localhost:8000/ws/query/5c4f15d1

# Receives events as they occur:
# ORCHESTRATOR_DONE
# SCRAPER_STARTED
# CHUNKS_COLLECTED
# ANALYST_DONE
# QUERY_DONE
```

### Example 3: Check System Status

```bash
curl http://localhost:8000/api/status

# Returns available providers, scraper status, etc.
```

## Pagination

List endpoints support pagination:

```bash
# Get 25 items, skip first 50
curl "http://localhost:8000/api/history?limit=25&offset=50"
```
