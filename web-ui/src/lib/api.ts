import axios from 'axios';

const API_BASE = '/api';

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json'
  }
});

export interface QuerySubmitResponse {
  query_id: string;
}

export interface QuerySubmissionOptions {
  query: string;
  focusArea?: string;
  llmRatio?: number;
  scraperRatio?: number;
}

export interface QueryHistoryItem {
  query_id: string;
  query_text: string;
  profile: string;
  confidence: number;
  created_at: number;
}

export interface QueryResult {
  query_id: string;
  answer: string;
  confidence: number;
  profile: string;
  duration_ms: number;
  plan?: Record<string, unknown>;
  sources?: string[];
}

export interface UsageEntry {
  name?: string;
  provider?: string;
  usage_pct: number;
  value?: number;
  calls?: number;
  chunks?: number;
}

export interface StageBreakdownItem {
  name: string;
  value: number;
  usage_pct: number;
}

export interface ExecutionStageDetail {
  id: string;
  name: string;
  status: string;
  latency_ms: number;
  metrics: Record<string, any>;
  logs: string[];
  api_calls: Array<Record<string, any>>;
  scraper_calls: Array<Record<string, any>>;
  chunks: {
    raw: Array<Record<string, any>>;
    scored: Array<Record<string, any>>;
    filtered: Array<Record<string, any>>;
  };
}

export interface ExecutionGraph {
  nodes: Array<Record<string, any>>;
  edges: Array<{ from: string; to: string }>;
}

export interface QueryExecution {
  query_id: string;
  summary: {
    query: string;
    profile: string;
    confidence: number;
    duration_ms: number;
    plan: Record<string, any>;
    controls: Record<string, any>;
    execution_metrics: Record<string, any>;
    sources: string[];
  };
  graph: ExecutionGraph;
  usage: {
    providers: UsageEntry[];
    scrapers: UsageEntry[];
    total_tokens: number;
  };
  stages: {
    breakdown: StageBreakdownItem[];
    metrics: Record<string, number>;
    thought_chain: Array<Record<string, any>>;
    details?: Record<string, ExecutionStageDetail>;
  };
  chunks: {
    raw?: Array<Record<string, any>>;
    scored?: Array<Record<string, any>>;
    filtered: Array<Record<string, any>>;
    counts: {
      filtered: number;
      raw: number;
      scored: number;
    };
  };
  debug: {
    api_calls: number;
    scraper_calls: number;
    orchestrator_plan: Record<string, any> | null;
  };
}

export const api = {
  // Query Management
  submitQuery: ({ query, focusArea, llmRatio = 70, scraperRatio = 30 }: QuerySubmissionOptions) => 
    apiClient.post<QuerySubmitResponse>('/query', {
      query,
      focus_area: focusArea,
      llm_ratio: llmRatio,
      scraper_ratio: scraperRatio,
    }),
  
  getQuery: (queryId: string) => 
    apiClient.get<QueryResult>(`/queries/${queryId}`),

  getExecution: (queryId: string) =>
    apiClient.get<QueryExecution>(`/queries/${queryId}/execution`),
  
  getHistory: (limit = 50) => 
    apiClient.get<{ queries: QueryHistoryItem[] }>('/history', { params: { limit } }),
  
  deleteQuery: (queryId: string) => 
    apiClient.delete(`/queries/${queryId}`),

  // WebSocket
  connectQueryStream: (queryId: string) => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    return new WebSocket(`${protocol}://${host}/ws/query/${queryId}`);
  }
};

export default api;
