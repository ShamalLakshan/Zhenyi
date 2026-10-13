import React, { useState, useEffect } from 'react';
import { Search, ExternalLink, X, BookOpen, Layers, ShieldCheck } from 'lucide-react';
import { ResearchChunk } from '../lib/types';
import { getSessionChunks } from '../lib/api';

interface EvidenceLensProps {
  sessionId: string | null;
  isOpen: boolean;
  onClose: () => void;
  initialQuery?: string;
}

export const EvidenceLens: React.FC<EvidenceLensProps> = ({
  sessionId,
  isOpen,
  onClose,
  initialQuery = '',
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [chunks, setChunks] = useState<ResearchChunk[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
    }
  }, [initialQuery]);

  useEffect(() => {
    if (isOpen && sessionId) {
      loadChunks(query);
    }
  }, [isOpen, sessionId]);

  const loadChunks = async (searchQuery: string) => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const data = await getSessionChunks(sessionId, searchQuery.trim() || undefined);
      setChunks(data);
    } catch (err) {
      console.error('Failed to load chunks:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadChunks(query);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-[540px] bg-[#0c0c0e] border-l border-zinc-800 shadow-2xl z-50 flex flex-col font-sans select-text">
      {/* ── Drawer Header ────────────────────────────────────────── */}
      <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-[#0e0e11]">
        <div className="flex items-center gap-2">
          <BookOpen size={15} className="text-zinc-400" />
          <span className="font-mono text-xs font-semibold tracking-wider text-zinc-100 uppercase">
            EVIDENCE LENS // FULL PROVENANCE
          </span>
          <span className="font-mono text-[10px] text-zinc-400 border border-zinc-800 px-1 py-0.5 rounded-[2px]">
            {chunks.length} chunks
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-zinc-400 hover:text-zinc-100 rounded hover:bg-zinc-800 transition-colors"
        >
          <X size={15} />
        </button>
      </div>

      {/* ── Search Bar (SQLite FTS5 Local Search) ────────────────── */}
      <form onSubmit={handleSearchSubmit} className="p-3 border-b border-zinc-800 bg-[#09090b]">
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search retrieved evidence via SQLite FTS5..."
            className="w-full bg-[#151518] border border-zinc-700/80 rounded-[2px] pl-8 pr-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 font-mono"
          />
          <Search size={13} className="absolute left-2.5 top-2.5 text-zinc-400" />
        </div>
      </form>

      {/* ── Chunks Feed ──────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
        {loading ? (
          <div className="p-8 text-center text-xs font-mono text-zinc-400">
            Querying local FTS5 semantic index...
          </div>
        ) : chunks.length === 0 ? (
          <div className="p-8 text-center text-xs font-mono text-zinc-400">
            No research chunks match query in this session.
          </div>
        ) : (
          chunks.map((chk) => (
            <div
              key={chk.id}
              className="p-3 bg-[#121215] border border-zinc-800/90 rounded-[2px] space-y-2 text-xs"
            >
              <div className="flex items-center justify-between font-mono text-[10px] text-zinc-400">
                <div className="flex items-center gap-1.5">
                  <span className="uppercase font-semibold text-zinc-300 px-1 py-0.5 bg-zinc-800/80 rounded-[2px]">
                    {chk.source}
                  </span>
                  {chk.score > 0 && <span>Score: {chk.score.toFixed(1)}</span>}
                </div>
                {chk.url && (
                  <a
                    href={chk.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-zinc-400 hover:text-zinc-200"
                  >
                    <span className="truncate max-w-[140px]">{chk.url.replace('https://', '')}</span>
                    <ExternalLink size={9} />
                  </a>
                )}
              </div>

              {chk.title && (
                <div className="font-semibold text-zinc-100 font-sans text-xs">
                  {chk.title}
                </div>
              )}

              <p className="text-zinc-300 text-[11px] font-sans leading-relaxed whitespace-pre-wrap line-clamp-8 hover:line-clamp-none transition-all">
                {chk.content}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
