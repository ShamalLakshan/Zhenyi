import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json'
  }
});

export interface QuerySubmitResponse {
  query_id: string;
}

export interface QueryStatusResponse {
  status: string;
  // add other fields if known
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
}

export const api = {
  // Health & Status
  health: () => apiClient.get('/health'),
  status: () => apiClient.get('/api/status'),

  // Query Management
  submitQuery: (query: string, focusArea?: string) => 
    apiClient.post<QuerySubmitResponse>('/api/query', { query, focus_area: focusArea }),
  
  getQuery: (queryId: string) => 
    apiClient.get<QueryResult>(`/api/queries/${queryId}`),
  
  listQueries: (limit = 100, offset = 0) => 
    apiClient.get<{ queries: QueryHistoryItem[] }>('/api/queries', { params: { limit, offset } }),
  
  getHistory: (limit = 50) => 
    apiClient.get<{ queries: QueryHistoryItem[] }>('/api/history', { params: { limit } }),
  
  deleteQuery: (queryId: string) => 
    apiClient.delete(`/api/queries/${queryId}`),
  
  cancelQuery: (queryId: string) => 
    apiClient.post(`/api/cancel/${queryId}`),

  // Logs & Debug
  getLogs: (queryId: string) => 
    apiClient.get(`/api/logs/${queryId}`),
  
  getDebug: (queryId: string, stage: string | null = null) => 
    apiClient.get(`/api/debug/${queryId}`, { params: stage ? { stage } : {} }),

  // WebSocket
  connectQueryStream: (queryId: string) => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const backendUrl = API_BASE.replace(/^https?:\/\//, '');
    return new WebSocket(`${protocol}://${backendUrl}/ws/query/${queryId}`);
  }
};

export default api;
