export type Status = 'ready' | 'submitting' | 'running' | 'done' | 'error' | 'cancelled';

export interface Node {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  subtitle?: string;
  title?: string;
}

export interface Edge {
  from: string;
  to: string;
}

export interface Chunk {
  source: string;
  title?: string;
  text?: string;
  content?: string;
  url?: string;
  score?: number;
  index?: number;
  length?: number;
  [key: string]: any;
}
