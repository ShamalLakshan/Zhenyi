import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const api = {
  // Health & Status
  health: () => apiClient.get('/health'),
  status: () => apiClient.get('/api/status'),

  // Query Management
  submitQuery: (query, focusArea) => 
    apiClient.post('/api/query', { query, focus_area: focusArea }),
  
  getQuery: (queryId) => 
    apiClient.get(`/api/queries/${queryId}`),
  
  listQueries: (limit = 100, offset = 0) => 
    apiClient.get('/api/queries', { params: { limit, offset } }),
  
  getHistory: (limit = 50) => 
    apiClient.get('/api/history', { params: { limit } }),
  
  deleteQuery: (queryId) => 
    apiClient.delete(`/api/queries/${queryId}`),
  
  cancelQuery: (queryId) => 
    apiClient.post(`/api/cancel/${queryId}`),

  // Logs & Debug
  getLogs: (queryId) => 
    apiClient.get(`/api/logs/${queryId}`),
  
  getDebug: (queryId, stage = null) => 
    apiClient.get(`/api/debug/${queryId}`, { params: stage ? { stage } : {} }),

  // WebSocket
  connectQueryStream: (queryId) => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const backendUrl = API_BASE.replace(/^https?:\/\//, '')
    return new WebSocket(`${protocol}://${backendUrl}/ws/query/${queryId}`)
  }
}

export default api
