import express from 'express';
import path from 'path';
import { createServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { v4 as uuidv4 } from 'uuid';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const httpServer = createServer(app);
const wss = new WebSocketServer({ noServer: true });

const PORT = 3000;

app.use(express.json());



// --- Persistence ---
interface QueryHistoryItem {
  query_id: string;
  query_text: string;
  profile: string;
  confidence: number;
  created_at: number;
  answer?: string;
  duration_ms?: number;
}

const history: QueryHistoryItem[] = [];
const activeQueries = new Map<string, WebSocket[]>();

// --- API Endpoints ---

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.post('/api/query', async (req, res) => {
  const { query, focus_area } = req.body;
  if (!query) return res.status(400).json({ detail: 'Query is required' });

  const queryId = uuidv4();
  const historyItem: QueryHistoryItem = {
    query_id: queryId,
    query_text: query,
    profile: focus_area || 'General Research',
    confidence: 0,
    created_at: Date.now()
  };
  history.unshift(historyItem);

  // Start processing in the background (non-blocking)
  processQuery(queryId, query, focus_area);

  res.json({ query_id: queryId });
});

app.get('/api/queries/:id', (req, res) => {
  const item = history.find(h => h.query_id === req.params.id);
  if (!item) return res.status(404).json({ detail: 'Query not found' });
  res.json(item);
});

app.get('/api/history', (req, res) => {
  const limit = parseInt(req.query.limit as string) || 50;
  res.json({ queries: history.slice(0, limit) });
});

app.delete('/api/queries/:id', (req, res) => {
  const index = history.findIndex(h => h.query_id === req.params.id);
  if (index !== -1) {
    history.splice(index, 1);
    return res.status(204).send();
  }
  res.status(404).json({ detail: 'Not found' });
});

// --- Pipeline Processing Logic ---

async function processQuery(queryId: string, query: string, focusArea?: string) {
  const startTime = Date.now();
  
  const sendEvent = (event_type: string, data: any) => {
    const sockets = activeQueries.get(queryId);
    if (sockets) {
      const payload = JSON.stringify({ query_id: queryId, event_type, data });
      sockets.forEach(s => {
        if (s.readyState === WebSocket.OPEN) s.send(payload);
      });
    }
  };

  try {
    sendEvent('QUERY_STARTED', { query });
    await sleep(800);

    sendEvent('ORCHESTRATOR_DONE', { plan: 'Identify key themes and sources.' });
    await sleep(600);

    // Mock chunks
    const chunks = [
      { source: 'DeepMind Blog', title: 'The future of AI reasoning', text: 'Reasoning models are evolving to handle complex multi-step tasks...', index: 0 },
      { source: 'ArXiv', title: 'Large Language Models as Research Assistants', text: 'LLMs can synthesize vast amounts of information but require factual grounding...', index: 1 },
      { source: 'Nature', title: 'Ethics in AI Research', text: 'Ethical considerations are paramount when deploying autonomous research agents...', index: 2 }
    ];
    sendEvent('CHUNKS_COLLECTED', { chunks, total_chunks: 3 });
    await sleep(1000);

    sendEvent('CHUNKS_FILTERED', { kept: 2, total: 3, filtered_chunks: chunks.slice(0, 2) });
    await sleep(800);

    // Mock synthesis result
    const answer = "Research synthesis generated successfully. Based on the collected sources, this represents a synthesis of key findings related to your query.";

    sendEvent('ANALYST_DONE', { successful_analysts: 1 });
    await sleep(600);

    sendEvent('SYNTHESIZER_DONE', { confidence: 0.92 });
    await sleep(400);

    const duration = Date.now() - startTime;
    const finalResult = {
      answer,
      confidence: 0.92,
      profile: focusArea || 'Expert Analyst',
      duration_ms: duration
    };

    const historyItem = history.find(h => h.query_id === queryId);
    if (historyItem) {
      Object.assign(historyItem, finalResult);
    }

    sendEvent('QUERY_DONE', finalResult);
  } catch (error: any) {
    console.error('Process Error:', error);
    sendEvent('QUERY_ERROR', { error: error.message });
  }
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// --- WebSocket Handling ---

httpServer.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url!, `http://${request.headers.host}`);
  const pathname = url.pathname;
  
  if (pathname.startsWith('/ws/query/')) {
    const queryId = pathname.split('/').pop()!;
    wss.handleUpgrade(request, socket, head, (ws) => {
      if (!activeQueries.has(queryId)) activeQueries.set(queryId, []);
      activeQueries.get(queryId)!.push(ws);
      
      ws.on('close', () => {
        const sockets = activeQueries.get(queryId);
        if (sockets) {
          const index = sockets.indexOf(ws);
          if (index !== -1) sockets.splice(index, 1);
          if (sockets.length === 0) activeQueries.delete(queryId);
        }
      });
      
      wss.emit('connection', ws, request);
    });
  } else {
    socket.destroy();
  }
});

// --- Vite Production / Static ---

const distPath = path.join(process.cwd(), 'dist');
app.use(express.static(distPath));
app.get('*', (req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

httpServer.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running on port ${PORT}`);
});
