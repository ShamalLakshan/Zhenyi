import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "./ui/sheet";
import { ScrollArea } from "./ui/scroll-area";
import { Button } from "./ui/button";
import { Trash2, History, Search, ArrowRight } from "lucide-react";
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
      <SheetContent side="left" className="w-[350px] p-0 flex flex-col border-r border-white/5 bg-[#151815]/95 backdrop-blur-xl">
        <SheetHeader className="p-8 border-b border-white/5">
          <div className="p-3 mb-6 w-fit rounded-full bg-[#7A8D7A] flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-white rounded-sm rotate-45"></div>
          </div>
          <SheetTitle className="serif italic text-2xl text-[#E8E6E1] font-normal">
            Research History
          </SheetTitle>
          <SheetDescription className="text-white/40 text-xs">
            Review and rerun your previous intelligence reports.
          </SheetDescription>
        </SheetHeader>
        
        <div className="px-6 py-4 space-y-1">
          <div className="text-[10px] uppercase tracking-[0.2em] text-[#7A8D7A] font-bold px-3 mb-4 mt-2">Intelligence Archive</div>
          <div className="relative px-3 mb-4">
            <Search className="absolute left-6 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/20" />
            <input 
              type="text" 
              placeholder="Filter Archive..." 
              className="w-full bg-[#1D211D] border-none h-9 pl-10 pr-4 rounded-xl text-xs focus:outline-none focus:ring-1 focus:ring-[#7A8D7A]/50 text-white placeholder:text-white/10"
            />
          </div>
        </div>

        <ScrollArea className="flex-1 px-4">
          <div className="space-y-1 pb-8">
            {isLoading && queries.length === 0 ? (
              [1, 2, 3].map(i => (
                <div key={i} className="h-16 bg-[#1D211D] animate-pulse rounded-xl mx-2" />
              ))
            ) : queries.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <History className="w-8 h-8 text-white/10 mb-4" />
                <p className="text-xs font-medium text-white/20">Archive Empty</p>
              </div>
            ) : (
              <AnimatePresence initial={false}>
                {queries.map((item) => (
                  <motion.div
                    layout
                    key={item.query_id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -10 }}
                    className="group relative px-6 py-4 rounded-r-xl border-l-2 border-transparent hover:bg-[#7A8D7A]/5 hover:border-[#7A8D7A] cursor-pointer transition-all active:bg-[#7A8D7A]/10"
                    onClick={() => onSelect(item.query_id)}
                  >
                    <div className="flex justify-between items-start mb-1">
                       <span className="text-[9px] font-mono text-white/20 uppercase tracking-tighter">{item.query_id}</span>
                       <Button 
                         variant="ghost" 
                         size="icon" 
                         className="h-5 w-5 bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity hover:text-destructive p-0"
                         onClick={(e) => {
                           e.stopPropagation();
                           onDelete(item.query_id);
                         }}
                       >
                         <Trash2 className="w-3 h-3" />
                       </Button>
                    </div>
                    <p className="text-xs font-medium text-[#E8E6E1]/70 line-clamp-1 group-hover:text-white transition-colors">
                      {item.query_text}
                    </p>
                    <div className="mt-2 flex items-center justify-between text-[8px] font-bold text-[#7A8D7A] uppercase tracking-[0.1em]">
                       <div className="flex items-center gap-3">
                          <span className="flex items-center gap-1.5 grayscale opacity-70 group-hover:grayscale-0 group-hover:opacity-100 transition-all">
                            <span className="w-1 h-1 rounded-full bg-[#7A8D7A]" />
                            {Math.round(item.confidence * 100)}%
                          </span>
                       </div>
                       <ArrowRight className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100 -translate-x-2 group-hover:translate-x-0 transition-all" />
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
