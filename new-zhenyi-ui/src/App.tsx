import { useState, useEffect, useRef, useCallback } from "react";
import { Header } from "./components/Header";
import { ThemeProvider } from "./components/ThemeProvider";
import { QueryInput } from "./components/QueryInput";
import { PipelineFlow } from "./components/PipelineFlow";
import { ResultPanel } from "./components/ResultPanel";
import { HistorySidebar } from "./components/HistorySidebar";
import { ChunkViewer } from "./components/ChunkViewer";
import { TooltipProvider } from "./components/ui/tooltip";
import { Toaster } from "./components/ui/sonner";
import { toast } from "sonner";
import api, { QueryExecution, QueryHistoryItem, QueryResult } from "./lib/api";
import { Status, Node, Edge, Chunk } from "./lib/types";
import { Loader2, History, Zap } from "lucide-react";

export default function App() {
  const [status, setStatus] = useState<Status>('ready');
  const [currentQuery, setCurrentQuery] = useState("");
  const [queryId, setQueryId] = useState<string | null>(null);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [pipelineData, setPipelineData] = useState<any>({});
  const [execution, setExecution] = useState<QueryExecution | null>(null);
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [selectedChunk, setSelectedChunk] = useState<Chunk | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);

  // Load History
  const loadHistory = useCallback(async () => {
    try {
      setIsLoadingHistory(true);
      const res = await api.getHistory();
      setHistory(res.data.queries);
    } catch (err) {
      console.error("Failed to load history", err);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const loadExecution = useCallback(async (id: string) => {
    try {
      const res = await api.getExecution(id);
      const exec = res.data;
      setExecution(exec);

      const graphNodes: Node[] = (exec.graph?.nodes || []).map((node: any) => ({
        id: node.id,
        label: node.label,
        status: 'done',
        title: node.model ? `${node.provider || ''} ${node.model}`.trim() : node.type,
      }));
      setNodes(graphNodes);
      setEdges(exec.graph?.edges || []);
    } catch (error) {
      setExecution(null);
    }
  }, []);

  // Handle Pipeline Events
  const handlePipelineEvent = useCallback((event: any) => {
    if (!event.event_type) return;

    const { event_type, data } = event;
    
    setPipelineData((prev: any) => ({
      ...prev,
      [event_type]: data
    }));

    setNodes((prevNodes) => {
      const nodeMap = Object.fromEntries(prevNodes.map(n => [n.id, { ...n }]));

      switch(event_type) {
        case 'QUERY_STARTED':
          setEdges([
            { from: 'orchestrator', to: 'triage' },
            { from: 'triage', to: 'analysts' },
            { from: 'analysts', to: 'synthesizer' },
            { from: 'synthesizer', to: 'output' },
          ]);
          return [
            { id: 'orchestrator', label: 'Orchestrator', status: 'running', title: data.query },
            { id: 'triage', label: 'Triage', status: 'pending', subtitle: 'Scoring & Filtering' },
            { id: 'analysts', label: 'Analysis', status: 'pending', subtitle: 'Intelligence Slicing' },
            { id: 'synthesizer', label: 'Synthesis', status: 'pending', subtitle: 'Final Assembly' },
            { id: 'output', label: 'Output', status: 'pending' }
          ];
        
        case 'ORCHESTRATOR_DONE':
          if (nodeMap['orchestrator']) nodeMap['orchestrator'].status = 'done';
          if (nodeMap['triage']) nodeMap['triage'].status = 'running';
          break;

        case 'CHUNKS_COLLECTED':
          if (data.chunks) {
            data.chunks.forEach((chunk: any) => {
              const scraperId = `scraper-${(chunk.source || 'unknown').toLowerCase()}`;
              if (!nodeMap[scraperId]) {
                 nodeMap[scraperId] = { id: scraperId, label: chunk.source, status: 'done', title: 'Data Ingested' };
                 setEdges((prev) => {
                  const next = [...prev, { from: 'orchestrator', to: scraperId }, { from: scraperId, to: 'triage' }];
                  const seen = new Set<string>();
                  return next.filter((edge) => {
                    const key = `${edge.from}-${edge.to}`;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                  });
                 });
              }
            });
          }
          if (nodeMap['triage']) {
            nodeMap['triage'].status = 'running';
            nodeMap['triage'].title = `${data.total_chunks} chunks collected`;
          }
          break;

        case 'CHUNKS_FILTERED':
          if (nodeMap['triage']) {
            nodeMap['triage'].status = 'done';
            nodeMap['triage'].title = `Kept ${data.kept}/${data.total}`;
          }
          if (nodeMap['analysts']) nodeMap['analysts'].status = 'running';
          break;

        case 'ANALYST_DONE':
          if (nodeMap['analysts']) {
            nodeMap['analysts'].status = 'done';
            nodeMap['analysts'].title = `${data.successful_analysts} Analysts Complete`;
          }
          if (nodeMap['synthesizer']) nodeMap['synthesizer'].status = 'running';
          break;

        case 'SYNTHESIZER_DONE':
          if (nodeMap['synthesizer']) nodeMap['synthesizer'].status = 'done';
          if (nodeMap['output']) nodeMap['output'].status = 'running';
          break;

        case 'QUERY_DONE':
          if (nodeMap['output']) nodeMap['output'].status = 'done';
          setQueryResult(data);
          if (data.query_id) {
            loadExecution(data.query_id);
          }
          setStatus('done');
          loadHistory();
          toast.success("Synthesis complete.");
          break;

        case 'QUERY_ERROR':
          if (nodeMap['output']) nodeMap['output'].status = 'error';
          setStatus('error');
          toast.error(data.error || "Synthesis interrupted.");
          break;
      }
      return Object.values(nodeMap);
    });
  }, [loadExecution, loadHistory]);

  // Handle Query Submission
  const handleSubmitQuery = async (query: string, focusArea?: string) => {
    try {
      setStatus('submitting');
      setQueryResult(null);
      setPipelineData({});
      setExecution(null);
      setNodes([]);
      setEdges([]);
      setSelectedChunk(null);
      setCurrentQuery(query);
      
      const res = await api.submitQuery(query, focusArea);
      const newQueryId = res.data.query_id;
      setQueryId(newQueryId);
      setStatus('running');

      const ws = api.connectQueryStream(newQueryId);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        handlePipelineEvent(JSON.parse(event.data));
      };

      ws.onclose = () => {
        if (status === 'running') setStatus('done');
      };

    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Connection failure");
      setStatus('ready');
    }
  };

  const handleSelectHistory = async (id: string) => {
    try {
      const res = await api.getQuery(id);
      setQueryResult(res.data);
      setQueryId(id);
      loadExecution(id);
      const historyItem = history.find(h => h.query_id === id);
      if (historyItem) setCurrentQuery(historyItem.query_text);
      
      setStatus('done');
      setIsHistoryOpen(false);
    } catch (err) {
      toast.error("Cloud synchronization error");
    }
  };

  const handleDeleteHistory = async (id: string) => {
    try {
      await api.deleteQuery(id);
      setHistory(prev => prev.filter(h => h.query_id !== id));
      toast.success("Archive purged.");
    } catch (err) {
      toast.error("Cleanup failed.");
    }
  };

  const rawChunks: Chunk[] = pipelineData.CHUNKS_COLLECTED?.raw_chunks_full || pipelineData.CHUNKS_COLLECTED?.chunks || [];
  const scoredChunks: Chunk[] = (pipelineData.CHUNKS_SCORED?.scored_chunks || []).map((c: any) => ({ ...c, stage: 'scored' }));
  const filteredChunks: Chunk[] = (
    pipelineData.CHUNKS_FILTERED?.filtered_chunks || execution?.chunks?.filtered || []
  ).map((c: any) => ({
    ...c,
    text: c.text || c.content,
    score: c.score ?? c.relevance_score,
    stage: 'filtered',
  }));

  const allChunks: Chunk[] = [
    ...rawChunks.map((c: any) => ({ ...c, stage: 'raw' })),
    ...scoredChunks,
    ...filteredChunks,
  ].filter((v, i, a) => {
    const key = v.text || v.content || v.title;
    return a.findIndex(t => (t.text || t.content || t.title) === key) === i;
  });

  return (
    <ThemeProvider defaultTheme="dark">
      <TooltipProvider>
        <div className="h-screen bg-background text-zinc-100 flex flex-col selection:bg-primary/30 overflow-hidden">
          <Header status={status} onToggleHistory={() => setIsHistoryOpen(true)} />
          
          <main className="flex-1 grid grid-cols-[64px_1fr_360px] gap-3 p-3 overflow-hidden">
            
            {/* Sidebar Palette */}
            <aside className="bg-card border border-border rounded-2xl flex flex-col items-center py-6 gap-6 shadow-2xl">
              <div 
                className="w-10 h-10 rounded-xl bg-zinc-800 text-zinc-400 flex items-center justify-center cursor-pointer hover:text-white transition-colors"
                onClick={() => setIsHistoryOpen(true)}
              >
                <History className="w-5 h-5" />
              </div>
              <div className="w-10 h-10 rounded-xl bg-primary/20 text-primary flex items-center justify-center cursor-pointer">
                <Zap className="w-5 h-5" />
              </div>
              <div className="w-10 h-10 rounded-xl bg-zinc-800 text-zinc-400 flex items-center justify-center cursor-pointer hover:text-white transition-colors">
                 <Loader2 className={`w-5 h-5 ${status === 'running' ? 'animate-spin' : ''}`} />
              </div>
              <div className="mt-auto w-10 h-10 rounded-full bg-linear-to-br from-indigo-500 to-primary border border-white/10 shadow-lg" />
            </aside>

            {/* Main Stage (Graph/Result Area) */}
            <div className="flex-1 min-w-0 flex flex-col relative bg-card border border-border rounded-2xl shadow-2xl overflow-hidden">
              <div className="absolute inset-0 grid-background pointer-events-none" />
              {status === 'ready' || status === 'submitting' ? (
                <QueryInput onSubmit={handleSubmitQuery} isLoading={status === 'submitting'} />
              ) : queryResult ? (
                <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-2 gap-3 p-3 relative z-10">
                  <div className="min-h-0 overflow-hidden border border-border rounded-xl bg-zinc-950/10">
                    <ResultPanel 
                      answer={queryResult.answer} 
                      confidence={queryResult.confidence}
                      profile={queryResult.profile}
                      duration={queryResult.duration_ms}
                      query={currentQuery}
                      stageBreakdown={execution?.stages?.breakdown}
                      providerUsage={execution?.usage?.providers}
                      scraperUsage={execution?.usage?.scrapers}
                      sources={queryResult.sources || execution?.summary?.sources || []}
                    />
                  </div>
                  <div className="min-h-0 overflow-hidden border border-border rounded-xl bg-zinc-950/10 p-4">
                    <PipelineFlow 
                      nodes={nodes}
                      edges={edges}
                      onNodeClick={(id) => console.log('Node:', id)}
                    />
                  </div>
                </div>
              ) : (
                <div className="flex-1 overflow-hidden flex flex-col p-8 relative z-10">
                   <PipelineFlow 
                     nodes={nodes}
                     edges={edges}
                     onNodeClick={(id) => console.log('Node:', id)}
                   />
                </div>
              )}

              {/* Status Bar */}
              {status === 'running' && (
                <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-zinc-900/90 border border-border px-6 py-3 rounded-full backdrop-blur-md shadow-2xl flex items-center gap-4">
                  <div className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                  </div>
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] opacity-40">Intelligence Stream Active</span>
                </div>
              )}
            </div>

            {/* Right Interface Panel */}
            <aside className="bg-card border border-border rounded-2xl flex flex-col overflow-hidden shadow-2xl">
              <ChunkViewer 
                chunks={allChunks}
                groupedChunks={{
                  raw: rawChunks,
                  scored: scoredChunks,
                  filtered: filteredChunks,
                }}
                selectedChunk={selectedChunk}
                onSelect={setSelectedChunk}
              />
            </aside>
          </main>

          <HistorySidebar 
            isOpen={isHistoryOpen} 
            onClose={() => setIsHistoryOpen(false)}
            queries={history}
            onSelect={handleSelectHistory}
            onDelete={handleDeleteHistory}
            isLoading={isLoadingHistory}
          />
          
          <Toaster position="bottom-right" theme="dark" richColors />
        </div>
      </TooltipProvider>
    </ThemeProvider>
  );
}
