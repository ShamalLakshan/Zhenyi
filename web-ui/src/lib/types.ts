export type Status = 'ready' | 'submitting' | 'running' | 'done' | 'error' | 'cancelled';

export interface Session {
  id: string;
  title: string;
  focus_domain: string;
  research_mode: 'deep_research' | 'economy';
  created_at: number;
  updated_at: number;
  message_count: number;
  node_count: number;
}

export interface MessageMetadata {
  query_id?: string;
  confidence?: number;
  sources?: Array<string | { url?: string; title?: string }>;
  duration_ms?: number;
  [key: string]: any;
}

export interface Message {
  id: string;
  session_id: string;
  parent_message_id?: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  reasoning_trace?: string | null;
  status: 'done' | 'running' | 'error';
  metadata?: MessageMetadata;
  created_at: number;
}

export type NodeType = 'entity' | 'claim' | 'source' | 'hypothesis';

export interface GraphNode {
  id: string;
  session_id: string;
  origin_message_id?: string;
  node_type: NodeType;
  label: string;
  description?: string;
  confidence: number;
  metadata?: Record<string, any>;
  created_at: number;
}

export type RelationType = 'supports' | 'contradicts' | 'implements' | 'alternative_to' | 'cited_by' | 'subtopic';

export interface GraphEdge {
  id: string;
  session_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: RelationType;
  weight: number;
  evidence_text?: string;
  created_at: number;
}

export interface SessionGraph {
  session_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ResearchChunk {
  id: string;
  source: string;
  title: string;
  url: string;
  content: string;
  score: number;
  created_at?: number;
}

export interface ProviderQuota {
  provider: string;
  display_name: string;
  tier: number;
  default_model: string;
  total_keys: number;
  ready_keys: number;
  cooling_keys: number;
  exhausted_keys: number;
  disabled_keys: number;
  total_daily_quota: number;
  total_daily_used: number;
  tokens_used_today: number;
}

export interface KeyVaultSummary {
  providers: Record<string, ProviderQuota>;
  total_keys: number;
  total_ready_keys: number;
  timestamp: number;
}

export interface ApiKeyItem {
  id: string;
  provider: string;
  masked_key: string;
  tier: number;
  default_model: string;
  status: 'ready' | 'cooling_down' | 'exhausted' | 'disabled';
  daily_limit: number;
  daily_requests_made: number;
  cooldown_until?: number;
  last_latency_ms?: number;
  last_used_at?: number;
}

export interface ChatTurnResponse {
  session_id: string;
  turn_id: string;
  user_message: Message;
  assistant_message: Message;
  answer: string;
  confidence: number;
  sources: Array<string | { url?: string; title?: string }>;
  duration_ms: number;
  new_graph_nodes: GraphNode[];
  new_graph_edges: GraphEdge[];
  cumulative_graph: SessionGraph;
}

export interface ContradictionPair {
  edge_id: string;
  evidence_text?: string;
  weight: number;
  source_node: {
    id: string;
    label: string;
    description?: string;
    type: NodeType;
  };
  target_node: {
    id: string;
    label: string;
    description?: string;
    type: NodeType;
  };
  created_at: number;
}
