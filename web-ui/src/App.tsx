import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatStream } from './components/ChatStream';
import { KnowledgeGraphCanvas } from './components/KnowledgeGraphCanvas';
import { EvidenceLens } from './components/EvidenceLens';
import { KeyManagerModal } from './components/KeyManagerModal';
import { Session, Message, SessionGraph } from './lib/types';
import {
  getSessionMessages,
  getSessionGraph,
  submitChatTurn,
  connectTurnStream,
  cancelSessionTurn,
  reconcileSessionGraph,
} from './lib/api';

const ResizeDivider: React.FC<{
  onMouseDown: (e: React.MouseEvent) => void;
  isDragging: boolean;
  onDoubleClick?: () => void;
  title?: string;
}> = ({ onMouseDown, isDragging, onDoubleClick, title }) => (
  <div
    onMouseDown={onMouseDown}
    onDoubleClick={onDoubleClick}
    title={title || 'Drag to resize pane (Double-click to reset)'}
    className="group relative w-2 -mx-1 h-full cursor-col-resize z-30 flex items-center justify-center shrink-0 select-none"
  >
    <div
      className={`w-[2px] h-full transition-colors duration-150 ${
        isDragging
          ? 'bg-zinc-300 shadow-[0_0_8px_rgba(255,255,255,0.4)]'
          : 'bg-transparent group-hover:bg-zinc-600'
      }`}
    />
    <div className="absolute top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-zinc-850 border border-zinc-700/80 rounded-[2px] px-0.5 py-1 pointer-events-none shadow-md z-40 bg-zinc-900">
      <div className="w-0.5 h-3 flex flex-col justify-between items-center">
        <span className="w-0.5 h-0.5 bg-zinc-400 rounded-full" />
        <span className="w-0.5 h-0.5 bg-zinc-400 rounded-full" />
        <span className="w-0.5 h-0.5 bg-zinc-400 rounded-full" />
      </div>
    </div>
  </div>
);

export default function App() {
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeBranchLeafId, setActiveBranchLeafId] = useState<string | null>(null);
  const [graph, setGraph] = useState<SessionGraph | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const [activeStatusText, setActiveStatusText] = useState('');
  const [isEvidenceOpen, setIsEvidenceOpen] = useState(false);
  const [evidenceQuery, setEvidenceQuery] = useState('');
  const [isKeyManagerOpen, setIsKeyManagerOpen] = useState(false);

  // Pane width states with localStorage persistence
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const saved = localStorage.getItem('zhenyi_sidebar_width');
    return saved ? Math.max(200, Math.min(480, parseInt(saved, 10))) : 280;
  });

  const [graphWidth, setGraphWidth] = useState<number>(() => {
    const saved = localStorage.getItem('zhenyi_graph_width');
    return saved ? Math.max(320, Math.min(1200, parseInt(saved, 10))) : 500;
  });

  const [isGraphEnlarged, setIsGraphEnlarged] = useState(false);
  const prevGraphWidthRef = useRef(graphWidth);
  const [activeResizing, setActiveResizing] = useState<'sidebar' | 'graph' | null>(null);

  const handleToggleEnlargeGraph = () => {
    if (isGraphEnlarged) {
      setGraphWidth(prevGraphWidthRef.current || 500);
      setIsGraphEnlarged(false);
    } else {
      prevGraphWidthRef.current = graphWidth;
      const enlargedWidth = Math.max(700, Math.floor(window.innerWidth * 0.65));
      setGraphWidth(enlargedWidth);
      setIsGraphEnlarged(true);
    }
  };

  useEffect(() => {
    if (!activeResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (activeResizing === 'sidebar') {
        const newWidth = Math.max(200, Math.min(480, e.clientX));
        setSidebarWidth(newWidth);
        localStorage.setItem('zhenyi_sidebar_width', newWidth.toString());
      } else if (activeResizing === 'graph') {
        const maxGraphWidth = Math.max(320, window.innerWidth - sidebarWidth - 320);
        const newWidth = Math.max(320, Math.min(maxGraphWidth, window.innerWidth - e.clientX));
        setGraphWidth(newWidth);
        localStorage.setItem('zhenyi_graph_width', newWidth.toString());
        setIsGraphEnlarged(false);
      }
    };

    const handleMouseUp = () => {
      setActiveResizing(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [activeResizing, sidebarWidth]);

  const wsRef = useRef<WebSocket | null>(null);

  // Load session data when selected or active branch changes
  const loadSessionData = useCallback(async (sessionId: string, leafId: string | null) => {
    try {
      const [msgs, grp] = await Promise.all([
        getSessionMessages(sessionId, leafId || undefined),
        getSessionGraph(sessionId),
      ]);
      setMessages(msgs);
      setGraph(grp);
    } catch (err) {
      console.error('Error loading session data:', err);
    }
  }, []);

  const handleSelectSession = useCallback((session: Session) => {
    setCurrentSession(session);
    setActiveBranchLeafId(null);
    loadSessionData(session.id, null);
  }, [loadSessionData]);

  const handleSelectBranchLeaf = useCallback((leafId: string | null) => {
    setActiveBranchLeafId(leafId);
    if (currentSession) {
      loadSessionData(currentSession.id, leafId);
    }
  }, [currentSession, loadSessionData]);

  // Handle chat turn submission
  const handleSubmitTurn = async (
    query: string,
    parentId: string | null,
    llmRatio: number,
    scraperRatio: number
  ) => {
    if (!currentSession) return;

    setIsLoading(true);
    setActiveStatusText('Decomposing inquiry and planning scrapers...');

    const clientTurnId = Math.random().toString(36).substring(2, 10);
    setActiveTurnId(clientTurnId);

    // Connect WebSocket stream for real-time progress
    try {
      if (wsRef.current) wsRef.current.close();
      wsRef.current = connectTurnStream(clientTurnId, (evt) => {
        if (evt.event_type === 'SCRAPER_STARTED') {
          setActiveStatusText(`Scraping active sources: ${(evt.data?.scrapers || []).join(', ')}...`);
        } else if (evt.event_type === 'CHUNKS_COLLECTED') {
          setActiveStatusText(`Collected ${evt.data?.total_chunks || 0} evidence chunks...`);
        } else if (evt.event_type === 'TRIAGE_DONE') {
          setActiveStatusText(`Triage complete: filtered ${evt.data?.chunks_remaining || 0} relevant chunks...`);
        } else if (evt.event_type === 'ANALYST_START') {
          setActiveStatusText(`Distributing chunks across parallel analysts...`);
        } else if (evt.event_type === 'SYNTHESIZER_STARTED') {
          setActiveStatusText(`Synthesizing findings & extracting knowledge graph triples...`);
        }
      });
    } catch (wsErr) {
      console.debug('WebSocket stream notice:', wsErr);
    }

    try {
      const res = await submitChatTurn(currentSession.id, {
        message: query,
        parent_message_id: parentId,
        turn_id: clientTurnId,
        focus_domain: currentSession.focus_domain,
        llm_ratio: llmRatio,
        scraper_ratio: scraperRatio,
      });

      // Update state with new turn
      setMessages((prev) => [...prev, res.user_message, res.assistant_message]);
      if (res.cumulative_graph) {
        setGraph(res.cumulative_graph);
      }
    } catch (err: any) {
      console.error('Turn execution notice:', err);
      // In case of turn cancellation or partial completion, reload latest messages
      if (currentSession) {
        loadSessionData(currentSession.id, activeBranchLeafId);
      }
    } finally {
      setIsLoading(false);
      setActiveTurnId(null);
      setActiveStatusText('');
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    }
  };

  const handleCancelTurn = async () => {
    if (!currentSession || !activeTurnId) return;
    try {
      setActiveStatusText('Aborting research turn in progress...');
      await cancelSessionTurn(currentSession.id, activeTurnId);
      setTimeout(() => {
        if (currentSession) {
          loadSessionData(currentSession.id, activeBranchLeafId);
        }
      }, 400);
    } catch (err) {
      console.error('Cancel turn error:', err);
    }
  };

  const handleOpenEvidence = (citationQuery?: string) => {
    setEvidenceQuery(citationQuery || '');
    setIsEvidenceOpen(true);
  };

  const handleDivergeConcept = (concept: string) => {
    const parentId = messages.length > 0 ? messages[messages.length - 1].id : null;
    handleSubmitTurn(
      `Investigate concept in depth: ${concept}. Outline primary mechanisms and latest developments.`,
      parentId,
      70,
      30
    );
  };

  const handleFindCounterEvidence = (claim: string) => {
    const parentId = messages.length > 0 ? messages[messages.length - 1].id : null;
    handleSubmitTurn(
      `Search for counter-evidence, disputes, or contradictions against: "${claim}". What do critics or alternative studies report?`,
      parentId,
      40,
      60
    );
  };

  const handleReconcileGraph = async () => {
    if (!currentSession) return;
    try {
      const unified = await reconcileSessionGraph(currentSession.id);
      setGraph(unified);
    } catch (err) {
      console.error('Failed to reconcile graph:', err);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#09090b] text-zinc-100 select-none relative">
      {/* ── Overlay during active resizing to ensure mouse tracking is uninterrupted ── */}
      {activeResizing && (
        <div className="fixed inset-0 z-50 cursor-col-resize select-none pointer-events-auto bg-transparent" />
      )}

      {/* ── Pane 1: Left Navigation & Key Vault Telemetry ────────── */}
      <Sidebar
        currentSessionId={currentSession?.id || null}
        onSelectSession={handleSelectSession}
        activeBranchLeafId={activeBranchLeafId}
        onSelectBranchLeaf={handleSelectBranchLeaf}
        messages={messages}
        onOpenKeyManager={() => setIsKeyManagerOpen(true)}
        width={sidebarWidth}
      />

      {/* ── Splitter 1: Between Sidebar and Chat ─────────────── */}
      <ResizeDivider
        onMouseDown={(e) => {
          e.preventDefault();
          setActiveResizing('sidebar');
        }}
        onDoubleClick={() => {
          setSidebarWidth(280);
          localStorage.setItem('zhenyi_sidebar_width', '280');
        }}
        isDragging={activeResizing === 'sidebar'}
        title="Drag to resize sidebar (double-click to reset)"
      />

      {/* ── Pane 2: Center Multi-Turn Conversational Stream ─────── */}
      <ChatStream
        session={currentSession}
        messages={messages}
        activeBranchLeafId={activeBranchLeafId}
        onSelectBranchLeaf={handleSelectBranchLeaf}
        onSubmitTurn={handleSubmitTurn}
        isLoading={isLoading}
        activeStatusText={activeStatusText}
        onOpenEvidence={handleOpenEvidence}
        onCancelTurn={handleCancelTurn}
      />

      {/* ── Splitter 2: Between Chat and Knowledge Graph ────────── */}
      <ResizeDivider
        onMouseDown={(e) => {
          e.preventDefault();
          setActiveResizing('graph');
        }}
        onDoubleClick={() => {
          setGraphWidth(500);
          localStorage.setItem('zhenyi_graph_width', '500');
          setIsGraphEnlarged(false);
        }}
        isDragging={activeResizing === 'graph'}
        title="Drag to adjust chat / graph bar size (double-click to reset)"
      />

      {/* ── Pane 3: Right Dynamic Knowledge Graph Canvas ─────────── */}
      <KnowledgeGraphCanvas
        sessionId={currentSession?.id || null}
        graph={graph}
        onDivergeConcept={handleDivergeConcept}
        onFindCounterEvidence={handleFindCounterEvidence}
        onOpenEvidence={handleOpenEvidence}
        width={graphWidth}
        isEnlarged={isGraphEnlarged}
        onToggleEnlarge={handleToggleEnlargeGraph}
        onReconcileGraph={handleReconcileGraph}
      />

      {/* ── Evidence Lens Slide-Over Drawer ─────────────────────── */}
      <EvidenceLens
        sessionId={currentSession?.id || null}
        isOpen={isEvidenceOpen}
        onClose={() => setIsEvidenceOpen(false)}
        initialQuery={evidenceQuery}
      />

      {/* ── Dynamic Key Vault Modal ─────────────────────────────── */}
      <KeyManagerModal
        isOpen={isKeyManagerOpen}
        onClose={() => setIsKeyManagerOpen(false)}
      />
    </div>
  );
}
