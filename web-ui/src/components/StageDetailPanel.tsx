import { ScrollArea } from "./ui/scroll-area";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { X, Clock3, Braces, Database, Cpu } from "lucide-react";
import type { ExecutionStageDetail } from "../lib/api";
import type { Chunk } from "../lib/types";

interface StageDetailPanelProps {
  stageId: string;
  detail: ExecutionStageDetail | null;
  onClose: () => void;
  onSelectChunk: (chunk: Chunk) => void;
}

export function StageDetailPanel({ stageId, detail, onClose, onSelectChunk }: StageDetailPanelProps) {
  if (!detail) {
    return (
      <div className="absolute right-3 top-3 bottom-3 w-[min(520px,92vw)] rounded-2xl border border-zinc-800 bg-zinc-950/95 shadow-2xl z-40">
        <div className="h-full flex items-center justify-center text-zinc-500 text-sm">
          No stage details available for {stageId}
        </div>
      </div>
    );
  }

  const chunkCount =
    (detail.chunks?.raw?.length || 0) +
    (detail.chunks?.scored?.length || 0) +
    (detail.chunks?.filtered?.length || 0);

  return (
    <div className="absolute right-3 top-3 bottom-3 w-[min(560px,96vw)] rounded-2xl border border-zinc-800 bg-zinc-950/95 backdrop-blur-md shadow-2xl z-40 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/70">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] font-black text-zinc-500">Stage Inspector</p>
          <h3 className="text-sm font-bold text-zinc-100">{detail.name}</h3>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-[9px] uppercase tracking-wider border-zinc-700 text-zinc-300">
            {detail.status}
          </Badge>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <ScrollArea className="h-[calc(100%-61px)]">
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
              <p className="text-[9px] uppercase tracking-wider font-black text-zinc-500">Latency</p>
              <p className="text-sm font-bold text-zinc-100 mt-1 flex items-center gap-1">
                <Clock3 className="w-3.5 h-3.5 text-primary" />
                {Math.round(detail.latency_ms || 0)} ms
              </p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
              <p className="text-[9px] uppercase tracking-wider font-black text-zinc-500">API Calls</p>
              <p className="text-sm font-bold text-zinc-100 mt-1 flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-primary" />
                {(detail.api_calls || []).length}
              </p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
              <p className="text-[9px] uppercase tracking-wider font-black text-zinc-500">Chunks</p>
              <p className="text-sm font-bold text-zinc-100 mt-1 flex items-center gap-1">
                <Database className="w-3.5 h-3.5 text-primary" />
                {chunkCount}
              </p>
            </div>
          </div>

          <section className="space-y-2">
            <p className="text-[10px] uppercase tracking-[0.2em] font-black text-zinc-500">Metrics</p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-3 space-y-1">
              {Object.entries(detail.metrics || {}).length > 0 ? (
                Object.entries(detail.metrics || {}).map(([key, value]) => (
                  <div key={key} className="flex justify-between text-[11px] text-zinc-300">
                    <span className="uppercase tracking-wider text-zinc-500">{key.replace(/_/g, " ")}</span>
                    <span className="font-semibold text-zinc-100">{String(value)}</span>
                  </div>
                ))
              ) : (
                <p className="text-[11px] text-zinc-500">No metrics for this stage.</p>
              )}
            </div>
          </section>

          <section className="space-y-2">
            <p className="text-[10px] uppercase tracking-[0.2em] font-black text-zinc-500">Logs</p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-3 space-y-1">
              {(detail.logs || []).length > 0 ? (
                (detail.logs || []).map((line, idx) => (
                  <p key={`${line}-${idx}`} className="text-[11px] text-zinc-300 leading-relaxed">{line}</p>
                ))
              ) : (
                <p className="text-[11px] text-zinc-500">No logs captured.</p>
              )}
            </div>
          </section>

          <section className="space-y-2">
            <p className="text-[10px] uppercase tracking-[0.2em] font-black text-zinc-500">API Calls</p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 divide-y divide-zinc-800">
              {(detail.api_calls || []).length > 0 ? (
                (detail.api_calls || []).map((call, idx) => (
                  <div key={`${call.agent_id || "call"}-${idx}`} className="p-3 text-[11px] text-zinc-300">
                    <div className="flex items-center justify-between">
                      <span className="font-bold">{call.provider || "unknown"} {call.model || ""}</span>
                      <span className="text-zinc-500">{Math.round(call.latency_ms || 0)} ms</span>
                    </div>
                    <p className="text-zinc-500 mt-1">{call.agent_id || "agent"} | in {call.tokens_in || 0} / out {call.tokens_out || 0}</p>
                  </div>
                ))
              ) : (
                <p className="p-3 text-[11px] text-zinc-500">No API calls recorded in this stage.</p>
              )}
            </div>
          </section>

          <section className="space-y-2">
            <p className="text-[10px] uppercase tracking-[0.2em] font-black text-zinc-500">Stage Chunks</p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-2 space-y-2">
              {[...(detail.chunks?.filtered || []), ...(detail.chunks?.scored || []), ...(detail.chunks?.raw || [])]
                .slice(0, 20)
                .map((chunk: any, idx: number) => (
                  <button
                    key={`${chunk.title || chunk.source || "chunk"}-${idx}`}
                    onClick={() => onSelectChunk(chunk as Chunk)}
                    className="w-full text-left rounded-lg border border-zinc-800 hover:border-primary/40 bg-zinc-950/70 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{chunk.source || "unknown"}</span>
                      <div className="flex items-center gap-1">
                        {chunk.is_llm_generated && (
                          <Badge variant="outline" className="text-[8px] h-4 border-indigo-400/40 text-indigo-300">llm</Badge>
                        )}
                        {typeof chunk.score === "number" && (
                          <Badge variant="outline" className="text-[8px] h-4 border-zinc-700 text-zinc-300">{Math.round(chunk.score * 100)}%</Badge>
                        )}
                      </div>
                    </div>
                    <p className="text-[11px] text-zinc-200 line-clamp-1 mt-1">{chunk.title || "Untitled chunk"}</p>
                    <p className="text-[10px] text-zinc-500 line-clamp-2 mt-1">{chunk.text || chunk.content || "No chunk content"}</p>
                  </button>
                ))}
              {chunkCount === 0 && (
                <p className="px-2 py-3 text-[11px] text-zinc-500">No stage chunks available.</p>
              )}
            </div>
          </section>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
            <p className="text-[9px] uppercase tracking-[0.2em] font-black text-zinc-500 mb-2 flex items-center gap-2">
              <Braces className="w-3.5 h-3.5" />
              JSON Inspector
            </p>
            <pre className="text-[10px] text-zinc-300 whitespace-pre-wrap wrap-break-word max-h-56 overflow-auto">
              {JSON.stringify(detail, null, 2)}
            </pre>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
