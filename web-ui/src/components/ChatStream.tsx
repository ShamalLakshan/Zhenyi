import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Send,
  Loader2,
  ChevronDown,
  ChevronRight,
  GitBranch,
  ExternalLink,
  BookOpen,
  Sliders,
  Terminal,
  Clock,
  Sparkle,
  Square,
} from 'lucide-react';
import { Session, Message } from '../lib/types';

interface ChatStreamProps {
  session: Session | null;
  messages: Message[];
  activeBranchLeafId: string | null;
  onSelectBranchLeaf: (id: string | null) => void;
  onSubmitTurn: (query: string, parentId: string | null, llmRatio: number, scraperRatio: number) => Promise<void>;
  isLoading: boolean;
  activeStatusText: string;
  onOpenEvidence: (citationQuery?: string) => void;
  onCancelTurn?: () => void;
}

export const ChatStream: React.FC<ChatStreamProps> = ({
  session,
  messages,
  activeBranchLeafId,
  onSelectBranchLeaf,
  onSubmitTurn,
  isLoading,
  activeStatusText,
  onOpenEvidence,
  onCancelTurn,
}) => {
  const [input, setInput] = useState('');
  const [llmRatio, setLlmRatio] = useState(70);
  const [scraperRatio, setScraperRatio] = useState(30);
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
  const [parentBranchTarget, setParentBranchTarget] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, activeStatusText]);

  const toggleReasoning = (id: string) => {
    setExpandedReasoning((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    setInput('');
    const parentId = parentBranchTarget || (messages.length > 0 ? messages[messages.length - 1].id : null);
    await onSubmitTurn(text, parentId, llmRatio, scraperRatio);
    setParentBranchTarget(null);
  };

  const handleBranchFrom = (msgId: string) => {
    setParentBranchTarget(msgId);
    textareaRef.current?.focus();
  };

  return (
    <section className="flex-1 h-screen flex flex-col bg-[#09090b] text-zinc-100 select-text overflow-hidden min-w-[320px]">
      {/* ── Header & Breadcrumbs ─────────────────────────────────── */}
      <div className="px-5 py-3 border-b border-zinc-800 bg-[#0c0c0e] flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-zinc-400 font-semibold tracking-wide uppercase">INVESTIGATION:</span>
          <span className="font-sans font-medium text-zinc-200 truncate max-w-md">
            {session ? session.title : 'No Session Selected'}
          </span>
          {session && (
            <span className="font-mono text-[10px] bg-zinc-900 border border-zinc-700/60 px-1.5 py-0.5 rounded-[2px] text-zinc-400">
              {session.focus_domain}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 font-mono text-[11px] text-zinc-400">
          <button
            onClick={() => onOpenEvidence()}
            className="flex items-center gap-1.5 px-2 py-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded-[2px] transition-colors"
          >
            <BookOpen size={12} />
            <span>Evidence Lens</span>
          </button>
        </div>
      </div>

      {/* ── Breadcrumb Lineage Navigator (Phase 5 Backtracking) ──── */}
      {messages.some((m) => m.role === 'user') && (
        <div className="px-5 py-1.5 bg-[#0a0a0c] border-b border-zinc-800/80 flex items-center gap-1.5 overflow-x-auto text-[11px] font-mono scrollbar-none select-none">
          <span className="text-[10px] text-zinc-400 font-semibold uppercase tracking-wider mr-1">PATH:</span>
          <button
            onClick={() => onSelectBranchLeaf(null)}
            className={`px-1.5 py-0.5 rounded-[2px] border ${
              !activeBranchLeafId ? 'bg-zinc-800 text-zinc-100 border-zinc-700 font-medium' : 'text-zinc-400 hover:text-zinc-200 border-transparent hover:border-zinc-800'
            } transition-colors`}
          >
            LATEST
          </button>
          {messages
            .filter((m) => m.role === 'user')
            .map((turn, index, arr) => {
              const isCurrent = activeBranchLeafId === turn.id;
              const snippet = turn.content.length > 20 ? turn.content.slice(0, 20) + '...' : turn.content;
              return (
                <React.Fragment key={turn.id}>
                  <span className="text-zinc-700">/</span>
                  <button
                    onClick={() => onSelectBranchLeaf(turn.id)}
                    title={`Backtrack to Turn #${index + 1}: ${turn.content}`}
                    className={`flex items-center gap-1 px-1.5 py-0.5 rounded-[2px] border whitespace-nowrap ${
                      isCurrent
                        ? 'bg-zinc-800 text-zinc-100 border-zinc-600 font-semibold'
                        : 'text-zinc-400 hover:text-zinc-200 border-transparent hover:border-zinc-800'
                    } transition-colors`}
                  >
                    <span className="text-zinc-400">T#{index + 1}</span>
                    <span className="font-sans text-[11px] text-zinc-300 max-w-[120px] truncate">{snippet}</span>
                  </button>
                </React.Fragment>
              );
            })}
        </div>
      )}

      {/* ── Active Branch Deviation Banner ──────────────────────── */}
      {parentBranchTarget && (
        <div className="px-5 py-1.5 bg-zinc-900/90 border-b border-zinc-800 text-[11px] font-mono flex items-center justify-between text-zinc-300">
          <div className="flex items-center gap-2">
            <GitBranch size={12} className="text-zinc-400" />
            <span>Diverging from turn:</span>
            <span className="text-zinc-100 font-semibold">{parentBranchTarget.slice(0, 12)}...</span>
          </div>
          <button
            onClick={() => setParentBranchTarget(null)}
            className="text-zinc-400 hover:text-zinc-100 underline text-[10px]"
          >
            Cancel Deviation
          </button>
        </div>
      )}

      {/* ── Messages Feed ────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {messages.length === 0 && !isLoading && (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto text-zinc-400 space-y-3">
            <Terminal size={32} className="text-zinc-600 stroke-[1.5]" />
            <div className="font-mono text-xs uppercase tracking-wider text-zinc-400">RESEARCH TERMINAL READY</div>
            <p className="text-xs font-sans text-zinc-400 leading-relaxed">
              Submit any deep inquiry, technical dilemma, or hypothesis. Zhenyi will decompose the problem, orchestrate scrapers,
              extract knowledge graph triples, and map verifiable claims.
            </p>
          </div>
        )}

        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isReasoningOpen = !!expandedReasoning[msg.id];

          return (
            <div
              key={msg.id}
              className={`flex flex-col ${
                isUser ? 'items-end' : 'items-start'
              }`}
            >
              {/* Message Header */}
              <div className="flex items-center gap-2 mb-1.5 px-1 font-mono text-[10px] text-zinc-400">
                <span className="font-semibold uppercase text-zinc-400">{isUser ? 'OPERATOR' : 'ZHENYI // AGENT'}</span>
                <span>•</span>
                <span>{new Date(msg.created_at * 1000).toLocaleTimeString()}</span>
                {!isUser && (
                  <button
                    onClick={() => handleBranchFrom(msg.id)}
                    title="Fork or diverge research from this turn"
                    className="hover:text-zinc-200 ml-2 flex items-center gap-1 border border-zinc-800 px-1 py-0.5 rounded-[2px]"
                  >
                    <GitBranch size={10} />
                    <span>Diverge</span>
                  </button>
                )}
              </div>

              {/* Message Body */}
              <div
                className={`max-w-3xl rounded-[3px] border ${
                  isUser
                    ? 'bg-[#151518] border-zinc-700/80 text-zinc-100 p-3.5 text-xs font-sans leading-relaxed'
                    : 'bg-[#101013] border-zinc-800/90 text-zinc-200 p-4 text-xs font-sans leading-relaxed w-full'
                }`}
              >
                {/* Collapsible Reasoning Trace (for Assistant turns) */}
                {!isUser && msg.reasoning_trace && (
                  <div className="mb-3 border border-zinc-800 bg-[#09090b] rounded-[2px]">
                    <button
                      onClick={() => toggleReasoning(msg.id)}
                      className="w-full px-2.5 py-1.5 flex items-center justify-between text-[11px] font-mono text-zinc-400 hover:text-zinc-200"
                    >
                      <div className="flex items-center gap-1.5">
                        <Clock size={11} />
                        <span>AGENT REASONING & STRATEGY</span>
                      </div>
                      {isReasoningOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    </button>
                    {isReasoningOpen && (
                      <div className="px-3 py-2 border-t border-zinc-800 text-[11px] font-mono text-zinc-400 whitespace-pre-wrap leading-normal bg-zinc-950/60">
                        {msg.reasoning_trace}
                      </div>
                    )}
                  </div>
                )}

                {/* Markdown Content */}
                <div className="prose prose-invert max-w-none text-xs space-y-2 [&>h1]:text-sm [&>h1]:font-mono [&>h1]:font-semibold [&>h2]:text-xs [&>h2]:font-mono [&>h2]:font-semibold [&>h3]:text-xs [&>h3]:font-mono [&>p]:leading-relaxed [&>ul]:list-disc [&>ul]:pl-4 [&>ol]:list-decimal [&>ol]:pl-4 [&>pre]:bg-[#09090b] [&>pre]:border [&>pre]:border-zinc-800 [&>pre]:p-2.5 [&>pre]:rounded-[2px] [&>table]:border [&>table]:border-zinc-800 [&>th]:border [&>th]:border-zinc-800 [&>th]:p-1.5 [&>td]:border [&>td]:border-zinc-800 [&>td]:p-1.5">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>

                {/* Citations / Sources Footer */}
                {!isUser && msg.metadata?.sources && msg.metadata.sources.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-zinc-800 flex flex-wrap gap-1.5 items-center">
                    <span className="font-mono text-[10px] text-zinc-400 uppercase mr-1">SOURCES:</span>
                    {msg.metadata.sources.map((src, i) => {
                      const url = typeof src === 'string' ? src : src?.url || '';
                      const title = typeof src === 'string' ? src.replace('https://', '').split('/')[0] : src?.title || `Source ${i + 1}`;
                      return (
                        <button
                          key={i}
                          onClick={() => onOpenEvidence(url || title)}
                          className="flex items-center gap-1 px-1.5 py-0.5 bg-[#18181b] hover:bg-zinc-800 border border-zinc-700/60 rounded-[2px] text-[10px] font-mono text-zinc-300 transition-colors"
                        >
                          <span className="truncate max-w-[180px]">{title}</span>
                          <ExternalLink size={9} className="text-zinc-400" />
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Live Execution Status (Phase 5 In-Flight Cancellation) */}
        {isLoading && (
          <div className="flex items-center justify-between p-3 bg-[#101013] border border-zinc-800 rounded-[2px] text-xs font-mono text-zinc-300">
            <div className="flex items-center gap-2.5">
              <Loader2 size={13} className="animate-spin text-zinc-400" />
              <span className="text-zinc-200">{activeStatusText || 'Conducting multi-agent research...'}</span>
            </div>
            {onCancelTurn && (
              <button
                onClick={onCancelTurn}
                title="Abort in-flight research turn"
                className="px-2 py-1 bg-zinc-900 hover:bg-red-950/40 text-red-400 hover:text-red-300 border border-zinc-800 hover:border-red-900/60 rounded-[2px] text-[10px] flex items-center gap-1.5 font-mono transition-colors"
              >
                <Square size={10} className="fill-current" />
                <span>Stop Turn</span>
              </button>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Input Workbench Footer ───────────────────────────────── */}
      <div className="p-3.5 border-t border-zinc-800 bg-[#0c0c0e] space-y-2">
        {/* Sliders & Ratios Control */}
        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400 px-1">
          <div className="flex items-center gap-3">
            <span className="text-zinc-400">BIAS RATIO:</span>
            <span>LLM: {llmRatio}%</span>
            <input
              type="range"
              min="10"
              max="90"
              step="5"
              value={llmRatio}
              onChange={(e) => {
                const val = Number(e.target.value);
                setLlmRatio(val);
                setScraperRatio(100 - val);
              }}
              className="w-20 accent-zinc-200 cursor-pointer h-1 bg-zinc-800"
            />
            <span>SCRAPERS: {scraperRatio}%</span>
          </div>
          <span className="text-zinc-400">PRESS ⌘+ENTER TO SUBMIT</span>
        </div>

        {/* Textarea Input */}
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              session
                ? "Enter research hypothesis, follow-up query, or prompt..."
                : "Create an investigation to start research..."
            }
            disabled={!session || isLoading}
            className="flex-1 bg-[#151518] border border-zinc-700/80 rounded-[2px] p-2.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 resize-none font-sans"
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || isLoading || !session}
            className="px-4 py-2.5 bg-zinc-100 hover:bg-zinc-300 disabled:opacity-30 disabled:hover:bg-zinc-100 text-zinc-950 font-mono text-xs font-semibold rounded-[2px] flex items-center gap-1.5 transition-colors h-[48px]"
          >
            {isLoading ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
            <span>Run</span>
          </button>
        </div>
      </div>
    </section>
  );
};
