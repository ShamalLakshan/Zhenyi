import React, { useState, useEffect } from 'react';
import {
  Plus,
  Compass,
  Cpu,
  Key,
  Database,
  Trash2,
  ChevronRight,
  GitBranch,
  ShieldAlert,
  CheckCircle2,
  Clock,
  Sliders,
} from 'lucide-react';
import { Session, Message, KeyVaultSummary, ProviderQuota } from '../lib/types';
import { listSessions, createSession, deleteSession, getKeySummary, setGatewayMode } from '../lib/api';

interface SidebarProps {
  currentSessionId: string | null;
  onSelectSession: (session: Session) => void;
  activeBranchLeafId: string | null;
  onSelectBranchLeaf: (messageId: string | null) => void;
  messages: Message[];
  onOpenKeyManager: () => void;
  width?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentSessionId,
  onSelectSession,
  activeBranchLeafId,
  onSelectBranchLeaf,
  messages,
  onOpenKeyManager,
  width,
}) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [keySummary, setKeySummary] = useState<KeyVaultSummary | null>(null);
  const [researchMode, setResearchMode] = useState<'deep_research' | 'economy'>('deep_research');
  const [isCreating, setIsCreating] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDomain, setNewDomain] = useState('general');

  useEffect(() => {
    loadSessions();
    loadKeyTelemetry();
    const interval = setInterval(loadKeyTelemetry, 15000);
    return () => clearInterval(interval);
  }, []);

  const loadSessions = async () => {
    try {
      const data = await listSessions();
      setSessions(data);
      if (data.length > 0 && !currentSessionId) {
        onSelectSession(data[0]);
      }
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  };

  const loadKeyTelemetry = async () => {
    try {
      const summary = await getKeySummary();
      setKeySummary(summary);
    } catch (err) {
      console.error('Failed to load key summary:', err);
    }
  };

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const session = await createSession({
        title: newTitle.trim() || undefined,
        focus_domain: newDomain,
        research_mode: researchMode,
      });
      setSessions([session, ...sessions]);
      onSelectSession(session);
      setIsCreating(false);
      setNewTitle('');
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!window.confirm('Delete this investigation and its knowledge graph?')) return;
    try {
      await deleteSession(id);
      const remaining = sessions.filter((s) => s.id !== id);
      setSessions(remaining);
      if (currentSessionId === id && remaining.length > 0) {
        onSelectSession(remaining[0]);
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const handleToggleMode = async () => {
    const nextMode = researchMode === 'deep_research' ? 'economy' : 'deep_research';
    try {
      await setGatewayMode(nextMode);
      setResearchMode(nextMode);
    } catch (err) {
      console.error('Failed to toggle mode:', err);
    }
  };

  // Extract branch turn points from current messages
  const userTurns = messages.filter((m) => m.role === 'user');

  return (
    <aside
      style={{
        width: width ? `${width}px` : undefined,
        minWidth: width ? `${width}px` : undefined,
      }}
      className="h-screen flex flex-col bg-[#0c0c0e] border-r border-zinc-800 text-zinc-300 select-none shrink-0 overflow-hidden"
    >
      {/* ── Studio Header ────────────────────────────────────────── */}
      <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img src="/logo.png" alt="Zhenyi Logo" className="w-4 h-4 rounded-[2px] object-contain shrink-0" />
          <span className="font-mono text-xs tracking-wider uppercase font-semibold text-zinc-100">
            ZHENYI // STUDIO
          </span>
          <span className="font-mono text-[10px] text-zinc-400 border border-zinc-800 px-1 py-0.5 rounded-[2px]">
            v2.0
          </span>
        </div>
        <button
          onClick={() => setIsCreating(!isCreating)}
          title="New Investigation"
          className="p-1.5 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 rounded-[2px] transition-colors"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* ── New Session Inline Form ──────────────────────────────── */}
      {isCreating && (
        <form onSubmit={handleCreateSession} className="p-3 bg-zinc-900/60 border-b border-zinc-800 space-y-2">
          <input
            type="text"
            placeholder="Investigation title (optional)"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            className="w-full bg-[#18181b] border border-zinc-700 px-2 py-1.5 text-xs text-zinc-100 rounded-[2px] focus:outline-none focus:border-zinc-500 font-sans"
            autoFocus
          />
          <div className="flex gap-2">
            <select
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              className="bg-[#18181b] border border-zinc-700 px-2 py-1 text-xs text-zinc-300 rounded-[2px] focus:outline-none flex-1 font-mono"
            >
              <option value="general">general</option>
              <option value="academic">academic/arxiv</option>
              <option value="biotech">biotech/pubmed</option>
              <option value="engineering">engineering/code</option>
              <option value="finance">finance/sec_edgar</option>
            </select>
            <button
              type="submit"
              className="px-2.5 py-1 bg-zinc-100 text-zinc-950 text-xs font-mono font-medium rounded-[2px] hover:bg-zinc-300 transition-colors"
            >
              Start
            </button>
          </div>
        </form>
      )}

      {/* ── Scrollable Investigation Sessions & Branches ─────────── */}
      <div className="flex-1 overflow-y-auto divide-y divide-zinc-800/40">
        {/* Session List */}
        <div className="p-2 space-y-1">
          <div className="px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-zinc-400 flex items-center justify-between">
            <span>INVESTIGATIONS ({sessions.length})</span>
            <Database size={11} />
          </div>
          {sessions.length === 0 ? (
            <div className="p-4 text-center text-xs text-zinc-400 font-mono">No investigations yet</div>
          ) : (
            sessions.map((s) => {
              const active = s.id === currentSessionId;
              return (
                <div
                  key={s.id}
                  onClick={() => onSelectSession(s)}
                  className={`group px-2.5 py-2 rounded-[2px] cursor-pointer flex items-start justify-between text-xs transition-colors ${
                    active
                      ? 'bg-zinc-900 border border-zinc-700 text-zinc-100'
                      : 'hover:bg-zinc-900/40 text-zinc-400 hover:text-zinc-200 border border-transparent'
                  }`}
                >
                  <div className="min-w-0 pr-2">
                    <div className="font-medium truncate leading-tight font-sans text-zinc-200">
                      {s.title}
                    </div>
                    <div className="font-mono text-[10px] text-zinc-400 mt-0.5 flex items-center gap-2">
                      <span>{s.focus_domain}</span>
                      <span>•</span>
                      <span>{s.message_count} turns</span>
                    </div>
                  </div>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 text-zinc-400 hover:text-rose-400 rounded transition-opacity"
                    title="Delete investigation"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Branch Tree Explorer (If active session has turns) */}
        {userTurns.length > 0 && (
          <div className="p-2 space-y-1">
            <div className="px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-zinc-400 flex items-center justify-between">
              <span>ACTIVE BRANCH LINEAGE</span>
              <GitBranch size={11} />
            </div>
            <div className="space-y-0.5 border-l border-zinc-800 ml-3 pl-2.5 my-1">
              <button
                onClick={() => onSelectBranchLeaf(null)}
                className={`w-full text-left px-2 py-1 text-[11px] font-mono rounded-[2px] truncate ${
                  activeBranchLeafId === null
                    ? 'text-zinc-100 bg-zinc-900 font-semibold'
                    : 'text-zinc-400 hover:text-zinc-300 hover:bg-zinc-900/30'
                }`}
              >
                * Latest Turn (Leaf)
              </button>
              {userTurns.map((turn, i) => (
                <button
                  key={turn.id}
                  onClick={() => onSelectBranchLeaf(turn.id)}
                  title={turn.content}
                  className={`w-full text-left px-2 py-1 text-[11px] font-mono rounded-[2px] truncate flex items-center gap-1.5 ${
                    activeBranchLeafId === turn.id
                      ? 'text-zinc-100 bg-zinc-900 font-semibold'
                      : 'text-zinc-400 hover:text-zinc-300 hover:bg-zinc-900/30'
                  }`}
                >
                  <span className="text-zinc-400">#{i + 1}</span>
                  <span className="truncate">{turn.content}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Key Vault Telemetry & Mode Controls Footer ───────────── */}
      <div className="p-3 border-t border-zinc-800 bg-[#09090b] space-y-2.5 text-xs">
        <div className="flex items-center justify-between text-[11px] font-mono">
          <div className="flex items-center gap-1.5 text-zinc-400">
            <Key size={12} />
            <span>VAULT POOL</span>
          </div>
          <button
            onClick={onOpenKeyManager}
            className="text-[10px] text-zinc-400 hover:text-zinc-200 underline font-mono"
          >
            Manage Keys
          </button>
        </div>

        {/* Quota Indicators */}
        {keySummary ? (
          <div className="grid grid-cols-2 gap-1.5 text-[11px] font-mono">
            <div className="bg-[#121215] border border-zinc-800/80 p-1.5 rounded-[2px]">
              <div className="text-[10px] text-zinc-400">KEYS READY</div>
              <div className="text-zinc-100 font-bold flex items-center gap-1 mt-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                {keySummary.total_ready_keys} / {keySummary.total_keys}
              </div>
            </div>
            <div className="bg-[#121215] border border-zinc-800/80 p-1.5 rounded-[2px]">
              <div className="text-[10px] text-zinc-400">PROVIDERS</div>
              <div className="text-zinc-100 font-bold mt-0.5">
                {Object.keys(keySummary.providers).length} Active
              </div>
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-zinc-400 font-mono">Polling gateway status...</div>
        )}

        {/* Research Mode Toggle */}
        <div className="pt-1 flex items-center justify-between border-t border-zinc-800/60">
          <span className="text-[10px] font-mono text-zinc-400 uppercase">MODE:</span>
          <button
            onClick={handleToggleMode}
            className="flex items-center gap-1.5 px-2 py-0.5 border border-zinc-700 bg-zinc-900 rounded-[2px] text-[10px] font-mono text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <Sliders size={10} />
            <span className="uppercase">{researchMode.replace('_', ' ')}</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
