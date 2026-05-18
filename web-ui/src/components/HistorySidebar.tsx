import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "./ui/sheet";
import { ScrollArea } from "./ui/scroll-area";
import { Button } from "./ui/button";
import { Trash2, History, Search, ArrowRight, Clock } from "lucide-react";
import { QueryHistoryItem } from "../lib/api";
import { motion, AnimatePresence } from "motion/react";

interface HistorySidebarProps {
  isOpen: boolean;
  onClose: () => void;
  queries: QueryHistoryItem[];
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  isLoading: boolean;
}

export function HistorySidebar({ isOpen, onClose, queries, onSelect, onDelete, isLoading }: HistorySidebarProps) {
  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent side="left" className="w-full sm:max-w-sm p-0 flex flex-col border-r bg-background/95 backdrop-blur-xl">
        <SheetHeader className="p-8 border-b">
          <div className="p-3 mb-6 w-fit rounded-2xl bg-primary/10 flex items-center justify-center border border-primary/20">
            <History className="w-5 h-5 text-primary" />
          </div>
          <SheetTitle className="text-2xl font-bold tracking-tight">
            Research Archive
          </SheetTitle>
          <SheetDescription className="text-xs uppercase tracking-widest font-bold opacity-40">
            Memory of intelligence reports
          </SheetDescription>
        </SheetHeader>
        
        <div className="px-6 py-4 space-y-1">
          <div className="relative px-2">
            <Search className="absolute left-6 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/40" />
            <input 
              type="text" 
              placeholder="Search history..." 
              className="w-full bg-muted/50 border-none h-10 pl-10 pr-4 rounded-xl text-xs focus:outline-none focus:ring-1 focus:ring-primary/30 transition-all font-medium"
            />
          </div>
        </div>

        <ScrollArea className="flex-1 px-4">
          <div className="space-y-2 pb-8">
            {isLoading && queries.length === 0 ? (
              [1, 2, 3].map(i => (
                <div key={i} className="h-20 bg-muted/30 animate-pulse rounded-2xl mx-2" />
              ))
            ) : queries.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center opacity-30">
                <History className="w-12 h-12 mb-4 stroke-1" />
                <p className="text-xs font-bold uppercase tracking-widest">No history yet</p>
              </div>
            ) : (
              <AnimatePresence initial={false}>
                {queries.map((item) => (
                  <motion.div
                    layout
                    key={item.query_id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="group relative px-6 py-5 rounded-2xl border border-transparent hover:bg-muted/50 hover:border-border cursor-pointer transition-all active:scale-[0.98]"
                    onClick={() => onSelect(item.query_id)}
                  >
                    <div className="flex justify-between items-start mb-2">
                       <span className="text-[10px] font-mono text-muted-foreground/50 tracking-tighter">ID: {item.query_id.slice(0, 8)}</span>
                       <Button 
                         variant="ghost" 
                         size="icon" 
                         className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity hover:text-destructive p-0 rounded-lg hover:bg-destructive/10"
                         onClick={(e) => {
                           e.stopPropagation();
                           onDelete(item.query_id);
                         }}
                       >
                         <Trash2 className="w-3.5 h-3.5" />
                       </Button>
                    </div>
                    <p className="text-sm font-semibold leading-tight line-clamp-2 pr-2 mb-3">
                      {item.query_text}
                    </p>
                    <div className="flex items-center justify-between text-[9px] font-bold text-muted-foreground uppercase tracking-widest">
                       <div className="flex items-center gap-4">
                          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600">
                            {Math.round(item.confidence * 100)}% Match
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3 opacity-40" />
                            {new Date(item.created_at).toLocaleDateString()}
                          </span>
                       </div>
                       <ArrowRight className="w-3 h-3 opacity-0 group-hover:opacity-100 -translate-x-2 group-hover:translate-x-0 transition-all text-primary" />
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
