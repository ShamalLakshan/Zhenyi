import { ScrollArea } from "./ui/scroll-area";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { ExternalLink, Copy, Search, Database, Layers, X } from "lucide-react";
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
  selectedChunk: Chunk | null;
  onSelect: (chunk: Chunk | null) => void;
}

export function ChunkViewer({ chunks, selectedChunk, onSelect }: ChunkViewerProps) {
  const [filter, setFilter] = useState("");

  const filteredChunks = chunks.filter(c => {
    const title = c.title || `${c.source} ${c.index ?? ''}`;
    const source = c.source || 'unknown';
    return title.toLowerCase().includes(filter.toLowerCase()) || 
           source.toLowerCase().includes(filter.toLowerCase());
  });

  return (
    <div className="flex flex-col h-full border-l border-white/5 bg-background">
      <div className="p-6 border-b border-white/5 space-y-4 flex-shrink-0">
        <div className="flex items-center justify-between">
          <h2 className="serif italic text-foreground text-lg font-normal flex items-center gap-2">
            <Database className="w-5 h-5 text-primary" />
            Citations
          </h2>
          <Badge variant="outline" className="font-bold text-[10px] uppercase tracking-[0.2em] text-primary border-primary/30 bg-primary/5">
            {chunks.length} Units
          </Badge>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50" />
          <input 
            type="text" 
            placeholder="Search Intelligence..." 
            className="w-full bg-muted border border-white/5 h-10 pl-10 pr-4 rounded-xl text-sm focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground transition-all font-medium"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative">
        <ScrollArea className="h-full w-full">
          <div className="px-4 py-4 space-y-3">
            {filteredChunks.map((chunk, i) => (
              <motion.div
                layout
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.01 }}
              >
                <div 
                  className={`group relative overflow-hidden transition-all cursor-pointer rounded-xl border p-3 hover:shadow-lg hover:shadow-primary/10 ${
                    selectedChunk === chunk ? 'bg-primary/10 border-primary shadow-md shadow-primary/20' : 'bg-muted/30 border-border hover:bg-muted/50 hover:border-primary/50'
                  }`}
                  onClick={() => onSelect(chunk === selectedChunk ? null : chunk)}
                >
                  <div className="space-y-2">
                    <div className="flex justify-between items-start gap-2">
                       <div className="flex flex-col gap-1 flex-1 min-w-0">
                         <div className="text-[10px] font-bold uppercase tracking-widest text-primary opacity-70">
                           {chunk.source || 'Unknown Source'}
                         </div>
                         {chunk.index !== undefined && (
                           <span className="text-[9px] text-muted-foreground opacity-50">Chunk #{chunk.index}</span>
                         )}
                       </div>
                       {chunk.score && (
                         <span className="text-[10px] font-mono font-bold text-muted-foreground flex-shrink-0">
                           {chunk.score.toFixed(3)}
                         </span>
                       )}
                       {chunk.length && (
                         <span className="text-[9px] text-muted-foreground opacity-50 flex-shrink-0">
                           {(chunk.length / 1000).toFixed(1)}K
                         </span>
                       )}
                    </div>
                    <h4 className="text-xs font-medium text-foreground line-clamp-2 group-hover:text-primary transition-colors leading-tight">
                      {chunk.title || `Data from ${chunk.source}`}
                    </h4>
                    <p className="text-[11px] text-muted-foreground line-clamp-3 leading-relaxed">
                      {chunk.text || chunk.content || `Source: ${chunk.source} | ${chunk.url || 'No URL available'}`}
                    </p>
                    {chunk.url && (
                      <a href={chunk.url} target="_blank" rel="noopener noreferrer" className="text-[10px] text-primary hover:underline truncate block">
                        {chunk.url}
                      </a>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
            {filteredChunks.length === 0 && (
              <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
                No chunks found
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Floating Detail Overlay */}
        <AnimatePresence>
          {selectedChunk && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="absolute inset-4 z-20 bg-background/95 backdrop-blur-sm rounded-2xl flex flex-col overflow-hidden shadow-2xl border border-border shadow-primary/20"
            >
              <div className="p-5 flex flex-col h-full gap-4">
                <div className="flex items-center justify-between flex-shrink-0">
                   <div className="space-y-1">
                     <Badge className="font-bold text-[10px] tracking-widest bg-primary/20 text-primary border-primary/30 border py-1 px-3 uppercase">
                       {selectedChunk.source}
                     </Badge>
                     <h3 className="serif italic text-foreground text-sm leading-tight font-semibold">
                       {selectedChunk.title || 'Knowledge Node'}
                     </h3>
                   </div>
                   <Button 
                     variant="ghost" 
                     size="icon"
                     onClick={() => onSelect(null)} 
                     className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg"
                   >
                     <X className="w-4 h-4" />
                   </Button>
                </div>
                
                <ScrollArea className="flex-1 bg-muted/30 rounded-lg p-4 border border-border">
                  <div className="text-sm leading-relaxed text-foreground/80 pr-4">
                    {selectedChunk.text || selectedChunk.content || 'No content available'}
                  </div>
                </ScrollArea>
                
                {(selectedChunk.url || selectedChunk.score) && (
                  <div className="flex items-center gap-3 pt-2 flex-shrink-0 text-[10px] text-muted-foreground space-x-4">
                    {selectedChunk.score && (
                      <span className="flex items-center gap-1">
                        <span className="text-primary font-bold">Relevance:</span>
                        <span className="text-foreground font-mono">{(selectedChunk.score * 100).toFixed(1)}%</span>
                      </span>
                    )}
                  </div>
                )}
                
                <div className="flex items-center gap-2 pt-2 flex-shrink-0">
                   {selectedChunk.url && (
                     <a 
                       href={selectedChunk.url} 
                       target="_blank" 
                       rel="noopener noreferrer"
                       className="flex-1 h-10 px-4 rounded-lg bg-primary text-primary-foreground text-[10px] font-bold uppercase tracking-widest flex items-center justify-center gap-2 hover:bg-primary/90 transition-colors"
                     >
                       <ExternalLink className="w-3.5 h-3.5" />
                       View Source
                     </a>
                   )}
                   <Button 
                     variant="outline" 
                     size="sm"
                     onClick={() => {
                       const text = selectedChunk.text || selectedChunk.content || '';
                       navigator.clipboard.writeText(text);
                     }}
                     className="h-10 px-4 rounded-lg text-[10px] font-bold uppercase tracking-widest flex items-center justify-center gap-2"
                   >
                     <Copy className="w-3.5 h-3.5" />
                     Copy
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
