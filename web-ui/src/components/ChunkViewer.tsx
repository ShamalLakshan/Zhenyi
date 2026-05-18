import { ScrollArea } from "./ui/scroll-area";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ExternalLink, Copy, Search, Database, X, Quote } from "lucide-react";
import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";

interface Chunk {
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

interface ChunkViewerProps {
  chunks: Chunk[];
  groupedChunks?: {
    raw?: Chunk[];
    scored?: Chunk[];
    filtered?: Chunk[];
  };
  selectedChunk: Chunk | null;
  onSelect: (chunk: Chunk | null) => void;
}

type ChunkTab = 'raw' | 'scored' | 'filtered' | 'all';

export function ChunkViewer({ chunks, groupedChunks, selectedChunk, onSelect }: ChunkViewerProps) {
  const [filter, setFilter] = useState("");
  const [activeTab, setActiveTab] = useState<ChunkTab>('all');

  const activeChunks =
    activeTab === 'all'
      ? chunks
      : groupedChunks?.[activeTab] || [];

  const filteredChunks = activeChunks.filter(c => {
    const title = c.title || `${c.source} ${c.index ?? ''}`;
    const source = c.source || 'unknown';
    return title.toLowerCase().includes(filter.toLowerCase()) || 
           source.toLowerCase().includes(filter.toLowerCase());
  });

  return (
    <div className="flex flex-col h-full bg-card">
      <div className="p-4 border-b border-zinc-800 space-y-4 shrink-0 bg-[#0c0c0e]/50">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-black uppercase tracking-[0.2em] text-zinc-500">Preview Sources</h3>
          <div className="w-2 h-2 bg-primary rounded-full animate-pulse shadow-[0_0_8px_rgba(79,70,229,0.8)]"></div>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" />
          <input 
            type="text" 
            placeholder="Search archive..." 
            className="w-full bg-background border border-zinc-800 h-9 pl-10 pr-4 rounded-xl text-[11px] outline-none focus:border-primary/50 transition-colors font-medium text-zinc-300"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <div className="grid grid-cols-4 gap-2">
          {(['all', 'raw', 'scored', 'filtered'] as ChunkTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`h-7 rounded-lg text-[10px] uppercase tracking-widest font-black border transition-colors ${
                activeTab === tab
                  ? 'bg-primary/15 border-primary/40 text-primary'
                  : 'bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative">
        <ScrollArea className="h-full w-full">
          <div className="px-3 py-4 space-y-3">
            {filteredChunks.map((chunk, i) => (
              <motion.div
                layout
                key={i}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.02 }}
              >
                <div 
                  className={`group relative overflow-hidden transition-all cursor-pointer rounded-xl border p-3.5 ${
                    selectedChunk === chunk ? 'bg-primary/10 border-primary/40 shadow-inner' : 'bg-zinc-900/40 border-zinc-800/60 hover:bg-zinc-800/40 hover:border-zinc-700'
                  }`}
                  onClick={() => onSelect(chunk === selectedChunk ? null : chunk)}
                >
                  <div className="space-y-2.5">
                    <div className="flex justify-between items-start gap-2">
                       <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                         <div className="text-[9px] font-black uppercase tracking-widest text-zinc-500 group-hover:text-primary transition-colors">
                           {chunk.source || 'Unknown Source'}
                         </div>
                       </div>
                       {typeof chunk.score === 'number' && (
                         <span className="text-[9px] font-mono font-bold text-zinc-600">
                           {chunk.score > 0 ? (chunk.score * 100).toFixed(0) : '0'}%
                         </span>
                       )}
                    </div>
                    <div className="flex items-center gap-2">
                      {chunk.stage && (
                        <Badge variant="outline" className="h-4 rounded px-1.5 text-[8px] uppercase tracking-widest border-zinc-700 text-zinc-400">
                          {chunk.stage}
                        </Badge>
                      )}
                      {chunk.is_llm_generated && (
                        <Badge variant="outline" className="h-4 rounded px-1.5 text-[8px] uppercase tracking-widest border-indigo-500/30 text-indigo-300">
                          llm
                        </Badge>
                      )}
                    </div>
                    <h4 className="text-[11px] font-bold line-clamp-2 leading-snug text-zinc-100 group-hover:text-white">
                      {chunk.title || `Intelligence Unit #${i}`}
                    </h4>
                    <p className="text-[10.5px] text-zinc-500 line-clamp-3 leading-relaxed font-medium">
                      {chunk.text || chunk.content || 'Data fragment captured'}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))}
            {filteredChunks.length === 0 && (
              <div className="flex flex-col items-center justify-center h-48 text-zinc-500 opacity-30 text-center px-4">
                <Database className="w-8 h-8 mb-3 stroke-1" />
                <p className="text-[10px] font-black uppercase tracking-widest leading-loose">Repository Exhausted</p>
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Detail Overlay */}
        <AnimatePresence>
          {selectedChunk && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="absolute inset-2 z-20 bg-zinc-950/95 backdrop-blur-xl rounded-2xl flex flex-col overflow-hidden shadow-[0_0_50px_-12px_rgba(0,0,0,0.8)] border border-zinc-800"
            >
              <div className="p-5 flex flex-col h-full gap-4">
                <div className="flex items-center justify-between shrink-0">
                   <div className="space-y-1">
                      <div className="flex items-center gap-2">
                         <Badge variant="outline" className="font-black text-[8px] tracking-[0.2em] h-5 uppercase px-2 bg-zinc-900 border-zinc-800">
                           {selectedChunk.source}
                         </Badge>
                         <span className="text-[9px] font-black uppercase text-primary animate-pulse">Live Citations</span>
                      </div>
                      <h3 className="text-sm font-bold leading-tight tracking-tight text-white line-clamp-2">
                        {selectedChunk.title || 'Intelligence Packet Detail'}
                      </h3>
                   </div>
                   <Button 
                     variant="ghost" 
                     size="icon"
                     onClick={() => onSelect(null)} 
                     className="h-8 w-8 text-zinc-600 hover:text-white hover:bg-zinc-900 rounded-lg shrink-0"
                   >
                     <X className="w-4 h-4" />
                   </Button>
                </div>
                
                <ScrollArea className="flex-1 bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
                  <div className="text-[12px] leading-relaxed text-zinc-300 whitespace-pre-wrap font-medium">
                    {selectedChunk.text || selectedChunk.content || 'No content available for this chunk.'}
                  </div>
                </ScrollArea>

                {(selectedChunk.provenance || selectedChunk.source_kind) && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-[10px] text-zinc-400 grid grid-cols-2 gap-2">
                    <div>kind: <span className="text-zinc-200">{selectedChunk.source_kind || selectedChunk.provenance?.source_kind || 'unknown'}</span></div>
                    <div>source id: <span className="text-zinc-200">{selectedChunk.provenance?.source_id || selectedChunk.source || 'n/a'}</span></div>
                    <div>provider: <span className="text-zinc-200">{selectedChunk.provenance?.provider_name || 'n/a'}</span></div>
                    <div>scraper: <span className="text-zinc-200">{selectedChunk.provenance?.scraper_name || 'n/a'}</span></div>
                  </div>
                )}
                
                <div className="flex items-center gap-2 pt-1 shrink-0">
                   {selectedChunk.url && (
                     <a 
                       href={selectedChunk.url} 
                       target="_blank" 
                       rel="noopener noreferrer"
                       className="flex-1 h-9 px-4 rounded-xl bg-primary text-white text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-2 hover:bg-primary/90 transition-all shadow-lg shadow-primary/20"
                     >
                       <ExternalLink className="w-3.5 h-3.5" />
                       Verify
                     </a>
                   )}
                   <Button 
                     variant="outline" 
                     className="h-9 px-4 rounded-xl text-[10px] font-black uppercase tracking-widest gap-2 bg-zinc-900 border-zinc-800"
                     onClick={() => {
                       const text = selectedChunk.text || selectedChunk.content || '';
                       navigator.clipboard.writeText(text);
                     }}
                   >
                     <Copy className="w-3.5 h-3.5 opacity-60" />
                     Extract
                   </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
