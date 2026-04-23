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
import api, { QueryHistoryItem, QueryResult } from "./lib/api";

type Status = 'ready' | 'submitting' | 'running' | 'done' | 'error' | 'cancelled';

interface PipelineNode {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  subtitle?: string;
  title?: string;
}

interface PipelineEdge {
  from: string;
  to: string;
}

export default function App() {
  const [status, setStatus] = useState<Status>('ready');
  const [currentQuery, setCurrentQuery] = useState("");
  const [currentQueryId, setCurrentQueryId] = useState<string | null>(null);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [nodes, setNodes] = useState<PipelineNode[]>([]);
  const [edges, setEdges] = useState<PipelineEdge[]>([]);
  const [pipelineData, setPipelineData] = useState<any>({});
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [selectedChunk, setSelectedChunk] = useState<any>(null);
  
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

  // Handle Pipeline Events
  const handlePipelineEvent = useCallback((event: any) => {
    if (event.type === 'ping' || !event.event_type) return;

    const { event_type, data } = event;
    
    setPipelineData((prev: any) => ({
      ...prev,
      [event_type]: data
    }));

    setNodes((prevNodes) => {
      const nodeMap = Object.fromEntries(prevNodes.map(n => [n.id, n]));
      const newEdges = [...edges];

      switch(event_type) {
        case 'QUERY_STARTED':
          return [
            { id: 'orchestrator', label: 'Orchestrator', status: 'running', title: data.query },
            { id: 'triage', label: 'Triage', status: 'pending', subtitle: 'Scoring & Filtering' },
            { id: 'analysts', label: 'Analysis', status: 'pending', subtitle: 'Contextual Slicing' },
            { id: 'synthesizer', label: 'Synthesis', status: 'pending', subtitle: 'Intelligence Assembly' },
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
                 // Normally we'd add edges here too
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
          setQueryResult({
            query_id: event.query_id,
            answer: data.answer,
            confidence: data.confidence,
            profile: data.profile,
            duration_ms: data.duration_ms
          });
          setStatus('done');
          loadHistory();
          toast.success("Intelligence report synthesized successfully.");
          break;

        case 'QUERY_ERROR':
          if (nodeMap['output']) nodeMap['output'].status = 'error';
          setStatus('error');
          toast.error("Research agent encountered an error: " + data.error);
          break;
      }
      return Object.values(nodeMap);
    });
  }, [edges, loadHistory]);

  // Handle Query Submission
  const handleSubmitQuery = async (query: string, focusArea?: string) => {
    try {
      setStatus('submitting');
      setQueryResult(null);
      setPipelineData({});
      setNodes([]);
      setSelectedChunk(null);
      setCurrentQuery(query);
      
      const res = await api.submitQuery(query, focusArea);
      const queryId = res.data.query_id;
      
      setCurrentQueryId(queryId);
      setStatus('running');

      const ws = api.connectQueryStream(queryId);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        handlePipelineEvent(JSON.parse(event.data));
      };

      ws.onclose = () => {
        if (status === 'running') setStatus('done');
      };

    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Submission failure");
      setStatus('error');
    }
  };

  const handleSelectHistory = async (id: string) => {
    try {
      const res = await api.getQuery(id);
      setQueryResult(res.data);
      setCurrentQuery(res.data.answer); // Or find the query text in history
      const historyItem = history.find(h => h.query_id === id);
      if (historyItem) setCurrentQuery(historyItem.query_text);
      
      setStatus('done');
      setIsHistoryOpen(false);
      setNodes([]); // Clear graph for historical view unless we fetch logs
    } catch (err) {
      toast.error("Failed to load historical data");
    }
  };

  const handleDeleteHistory = async (id: string) => {
    try {
      await api.deleteQuery(id);
      setHistory(prev => prev.filter(h => h.query_id !== id));
      toast.success("Historical record purged.");
    } catch (err) {
      toast.error("Failed to delete record.");
    }
  };

  const allChunks = [
    ...(pipelineData.CHUNKS_COLLECTED?.raw_chunks_full || pipelineData.CHUNKS_COLLECTED?.chunks || []),
    ...(pipelineData.CHUNKS_FILTERED?.filtered_chunks || []),
    ...(pipelineData.CHUNKS_SCORED?.scored_chunks || []),
  ].filter((v, i, a) => {
    const uniqueKey = v.text || v.content || `${v.source}-${v.index}`;
    return a.findIndex(t => (t.text || t.content || `${t.source}-${t.index}`) === uniqueKey) === i;
  });

  return (
    <ThemeProvider defaultTheme="dark">
      <TooltipProvider>
        <div className="min-h-screen bg-background text-foreground transition-colors duration-300 flex flex-col">
          <Header status={status} onToggleHistory={() => setIsHistoryOpen(true)} />
          
          <main className="flex-1 flex overflow-hidden gap-0">
            
            {/* Left Panel: Request/Response (flex-grow, independently scrollable) */}
            <div className="flex-1 min-w-0 border-r border-white/5 overflow-hidden flex flex-col">
              {status === 'ready' || status === 'submitting' ? (
                <QueryInput onSubmit={handleSubmitQuery} isLoading={status === 'submitting'} />
              ) : queryResult ? (
                <div className="flex-1 overflow-y-auto">
                  <ResultPanel 
                    answer={queryResult.answer} 
                    confidence={queryResult.confidence}
                    profile={queryResult.profile}
                    duration={queryResult.duration_ms}
                    query={currentQuery}
                  />
                </div>
              ) : status === 'running' ? (
                <div className="flex-1 overflow-y-auto flex flex-col">
                  <div className="flex-1 flex flex-col items-center justify-center p-8">
                    <PipelineFlow 
                      nodes={nodes}
                      edges={edges}
                      onNodeClick={(nodeId) => console.log('Clicked node:', nodeId)}
                    />
                  </div>
                  {allChunks.length > 0 && (
                    <div className="border-t border-white/5 p-4 bg-background/50">
                      <div className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">
                        Intelligence Gathered: {allChunks.length} Units
                      </div>
                      <div className="flex gap-2 flex-wrap">
                        {allChunks.slice(0, 3).map((chunk, i) => (
                          <div key={i} className="text-[10px] bg-primary/10 text-primary px-2 py-1 rounded-lg truncate max-w-xs border border-primary/20">
                            {chunk.source} · {chunk.title || `Unit #${chunk.index}`}
                          </div>
                        ))}
                        {allChunks.length > 3 && (
                          <div className="text-[10px] text-muted-foreground px-2 py-1">+{allChunks.length - 3} more</div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center p-8 text-center">
                  <div className="w-16 h-16 rounded-3xl bg-primary/10 flex items-center justify-center mb-6">
                    <Loader2 className="w-8 h-8 text-primary animate-spin" />
                  </div>
                  <h2 className="text-xl font-bold mb-2">Processing Query</h2>
                  <p className="text-sm text-muted-foreground max-w-sm">
                    Agent is currently gathering intelligence nodes and synthesizing a final research report.
                  </p>
                </div>
              )}
            </div>

            {/* Right Panel: Citations/Chunks (independently scrollable, always visible on md+) */}
            <div className="w-72 flex-shrink-0 overflow-hidden border-l border-white/5 hidden md:flex flex-col">
              <ChunkViewer 
                chunks={allChunks}
                selectedChunk={selectedChunk}
                onSelect={setSelectedChunk}
              />
            </div>
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

function Loader2(props: any) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}
