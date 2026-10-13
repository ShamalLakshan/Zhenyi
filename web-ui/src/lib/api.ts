import axios from 'axios';
import {
  Session,
  Message,
  SessionGraph,
  ResearchChunk,
  KeyVaultSummary,
  ApiKeyItem,
  ChatTurnResponse,
  ContradictionPair,
} from './types';

const API_BASE = '/api';

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Session APIs ─────────────────────────────────────────────────────────────

export async function listSessions(limit = 50, offset = 0): Promise<Session[]> {
  const res = await apiClient.get<Session[]>('/sessions', { params: { limit, offset } });
  return res.data;
}

export async function createSession(data: {
  title?: string;
  focus_domain?: string;
  research_mode?: string;
}): Promise<Session> {
  const res = await apiClient.post<Session>('/sessions', data);
  return res.data;
}

export async function getSession(sessionId: string): Promise<Session> {
  const res = await apiClient.get<Session>(`/sessions/${sessionId}`);
  return res.data;
}

export async function updateSession(
  sessionId: string,
  data: { title?: string; focus_domain?: string; research_mode?: string }
): Promise<Session> {
  const res = await apiClient.patch<Session>(`/sessions/${sessionId}`, data);
  return res.data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/sessions/${sessionId}`);
}

export async function getSessionMessages(
  sessionId: string,
  branchLeafId?: string
): Promise<Message[]> {
  const res = await apiClient.get<Message[]>(`/sessions/${sessionId}/messages`, {
    params: branchLeafId ? { branch_leaf_id: branchLeafId } : {},
  });
  return res.data;
}

export async function getSessionGraph(sessionId: string): Promise<SessionGraph> {
  const res = await apiClient.get<SessionGraph>(`/sessions/${sessionId}/graph`);
  return res.data;
}

export async function reconcileSessionGraph(sessionId: string): Promise<SessionGraph> {
  const res = await apiClient.post<SessionGraph>(`/sessions/${sessionId}/graph/reconcile`);
  return res.data;
}

export async function getSessionChunks(
  sessionId: string,
  query?: string
): Promise<ResearchChunk[]> {
  const res = await apiClient.get<ResearchChunk[]>(`/sessions/${sessionId}/chunks`, {
    params: query ? { q: query } : {},
  });
  return res.data;
}

export async function submitChatTurn(
  sessionId: string,
  turnData: {
    message: string;
    parent_message_id?: string | null;
    turn_id?: string;
    focus_domain?: string;
    research_mode?: string;
    llm_ratio?: number;
    scraper_ratio?: number;
  }
): Promise<ChatTurnResponse> {
  const res = await apiClient.post<ChatTurnResponse>(`/sessions/${sessionId}/chat`, turnData);
  return res.data;
}

// ── Key Vault APIs ───────────────────────────────────────────────────────────

export async function getKeySummary(): Promise<KeyVaultSummary> {
  const res = await apiClient.get<KeyVaultSummary>('/keys/summary');
  return res.data;
}

export async function listKeys(): Promise<ApiKeyItem[]> {
  const res = await apiClient.get<ApiKeyItem[]>('/keys');
  return res.data;
}

export async function createKey(data: {
  provider: string;
  api_key: string;
  model?: string;
  daily_limit?: number;
}): Promise<ApiKeyItem> {
  const res = await apiClient.post<ApiKeyItem>('/keys', data);
  return res.data;
}

export async function updateKey(
  keyId: string,
  data: { status?: string; model?: string; daily_limit?: number }
): Promise<ApiKeyItem> {
  const res = await apiClient.patch<ApiKeyItem>(`/keys/${keyId}`, data);
  return res.data;
}

export async function deleteKey(keyId: string): Promise<void> {
  await apiClient.delete(`/keys/${keyId}`);
}

export async function testKey(data: {
  provider: string;
  api_key: string;
  model?: string;
}): Promise<{ valid: boolean; latency_ms: number; message: string; model_used: string }> {
  const res = await apiClient.post('/keys/test', data);
  return res.data;
}

export async function setGatewayMode(mode: 'economy' | 'deep_research'): Promise<{ status: string; mode: string }> {
  const res = await apiClient.post(`/gateway/mode?mode=${mode}`);
  return res.data;
}

// ── Phase 5: Contradiction Radar & Export Studio APIs ───────────────────────

export async function getSessionContradictions(sessionId: string): Promise<ContradictionPair[]> {
  const res = await apiClient.get<ContradictionPair[]>(`/sessions/${sessionId}/contradictions`);
  return res.data;
}

export async function cancelSessionTurn(sessionId: string, turnId: string): Promise<void> {
  await apiClient.post(`/sessions/${sessionId}/cancel/${turnId}`);
}

export function getExportUrl(sessionId: string, format: 'markdown' | 'bibtex' | 'obsidian', branchLeafId?: string): string {
  let url = `/api/sessions/${sessionId}/export/${format}`;
  if (branchLeafId) {
    url += `?branch_leaf_id=${encodeURIComponent(branchLeafId)}`;
  }
  return url;
}

export function triggerExportDownload(sessionId: string, format: 'markdown' | 'bibtex' | 'obsidian', branchLeafId?: string): void {
  const link = document.createElement('a');
  link.href = getExportUrl(sessionId, format, branchLeafId);
  link.download = '';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// ── WebSocket Helper ─────────────────────────────────────────────────────────

export function connectTurnStream(
  turnId: string,
  onEvent: (event: any) => void,
  onError?: (err: any) => void
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const wsUrl = `${protocol}//${host}/ws/query/${turnId}`;

  const ws = new WebSocket(wsUrl);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch {
      // Ignore non-json ping/pongs
    }
  };

  if (onError) {
    ws.onerror = onError;
  }

  return ws;
}
