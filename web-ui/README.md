# LLM Research Council - Web UI

A modern React-based web interface for the LLM Research Council pipeline. Features real-time monitoring, interactive pipeline visualization, and detailed logging.

## Prerequisites

- Node.js 16+ and npm/yarn
- Backend server running on `http://localhost:8000`

## Installation

```bash
# Install dependencies
npm install

# Create .env file from example
cp .env.example .env
```

## Development

```bash
# Start development server (runs on http://localhost:5173)
npm run dev

# The Vite dev server proxies API calls to http://localhost:8000
```

## Build for Production

```bash
# Create optimized build
npm run build

# Preview production build
npm run preview
```

## Environment Variables

Edit `.env` to change API configuration:

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=localhost:8000
```

## Features

### Pipeline Visualization
- Interactive DAG graph showing pipeline stages
- Real-time node status updates (pending → running → done/error)
- Clickable nodes to view stage details

### Detail Panels
- Draggable, resizable floating panels
- View raw JSON data, logs, and debug info
- Copy to clipboard functionality
- Separate panels for each pipeline stage

### Query History
- Browse previous queries with pagination
- Click to re-run or inspect historical results
- Delete queries and associated logs
- Filter by profile and confidence

### Real-time Updates
- WebSocket connection for live pipeline events
- Automatic UI updates as pipeline progresses
- Connection status indicator

### System Status
- View available API keys and providers
- Scraper status and circuit breaker state
- Running query count

## Architecture

```
src/
├── main.jsx              # React entry point
├── App.jsx               # Main app component
├── api.js                # API client (axios + WebSocket)
├── App.css               # Global styles
└── components/
    ├── PipelineGraph.jsx # DAG visualization
    ├── DetailPanel.jsx   # Floating detail panels
    ├── QueryInput.jsx    # Query submission form
    ├── HistoryPanel.jsx  # Query history sidebar
    └── *.css             # Component styles
```

## API Integration

The UI communicates with the backend via:

- **REST API**: `/api/query`, `/api/queries`, `/api/logs`, `/api/debug`
- **WebSocket**: `/ws/query/{query_id}` for real-time events

Backend must be running before starting the UI.

## Troubleshooting

### Backend connection errors
- Ensure backend is running: `uvicorn server:app --reload`
- Check `VITE_API_URL` in `.env` matches backend URL

### WebSocket connection fails
- Verify backend WebSocket endpoint is accessible
- Check browser console for detailed error messages

### Styles not loading
- Clear browser cache
- Restart dev server: `npm run dev`

## Production Deployment

```bash
# Build
npm run build

# Output in dist/ folder - serve as static files
# Point nginx/Apache to dist/index.html for SPA routing
```

## License

Same as main project
