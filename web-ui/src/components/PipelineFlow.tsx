import { motion, AnimatePresence } from "motion/react";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";
import { 
  Target, 
  Search, 
  Filter, 
  Brain, 
  Zap, 
  CheckCircle2, 
  AlertCircle,
  Loader2,
  ChevronRight
} from "lucide-react";

interface Node {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  subtitle?: string;
  title?: string;
}

interface Edge {
  from: string;
  to: string;
}

interface PipelineFlowProps {
  nodes: Node[];
  edges: Edge[];
  onNodeClick: (nodeId: string) => void;
}

const iconMap = {
  orchestrator: Target,
  triage: Filter,
  analysts: Brain,
  synthesizer: Zap,
  output: CheckCircle2,
  scraper: Search
};

export function PipelineFlow({ nodes, edges, onNodeClick }: PipelineFlowProps) {
  // Group scraper nodes
  const coreNodes = nodes.filter(n => !n.id.startsWith('scraper-'));
  const scraperNodes = nodes.filter(n => n.id.startsWith('scraper-'));

  // Define fixed order for core nodes
  const order = ['orchestrator', 'triage', 'analysts', 'synthesizer', 'output'];
  const sortedCoreNodes = [...coreNodes].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));

  return (
    <div className="relative w-full h-full flex flex-col items-center justify-center p-8 bg-slate-50/50 dark:bg-slate-950/50 rounded-3xl border border-dashed border-muted-foreground/20">
      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-50">
         <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px]" />
      </div>

      <div className="relative z-10 flex flex-col items-center gap-12 w-full max-w-4xl">
        <div className="flex flex-wrap justify-center items-start gap-x-12 gap-y-16 w-full">
          {sortedCoreNodes.map((node, i) => {
            const Icon = (iconMap as any)[node.id] || Zap;
            const isLast = i === sortedCoreNodes.length - 1;
            
            return (
              <div key={node.id} className="relative flex items-center">
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.1 }}
                  className="group relative"
                >
                  <Card 
                    className={`relative w-40 p-4 border transition-all cursor-pointer hover:shadow-xl bg-card/30 backdrop-blur-sm ${
                      node.status === 'running' ? 'border-[#7A8D7A] ring-4 ring-[#7A8D7A]/10 shadow-lg shadow-[#7A8D7A]/20' : 
                      node.status === 'done' ? 'border-[#7A8D7A]/50 bg-[#7A8D7A]/5' : 
                      'border-white/5 bg-white/2'
                    }`}
                    onClick={() => onNodeClick(node.id)}
                  >
                    <div className="flex flex-col items-center text-center gap-2">
                       <div className={`p-2 rounded-lg ${
                         node.status === 'running' ? 'bg-[#7A8D7A] text-white' :
                         node.status === 'done' ? 'bg-[#7A8D7A] text-white' :
                         'bg-white/5 text-white/40'
                       }`}>
                         {node.status === 'running' ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />}
                       </div>
                       <div>
                         <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#7A8D7A]">{node.label}</h4>
                         <p className="text-[10px] text-white/40 font-medium truncate max-w-[120px] serif">
                           {node.title || node.subtitle || 'Waiting...'}
                         </p>
                       </div>
                    </div>
                    
                    {/* Status indicator on top right */}
                    <div className="absolute -top-2 -right-2">
                      {node.status === 'done' && (
                        <div className="bg-[#7A8D7A] text-white p-0.5 rounded-full shadow-sm">
                          <CheckCircle2 className="w-3 h-3" />
                        </div>
                      )}
                      {node.status === 'error' && (
                        <div className="bg-destructive text-destructive-foreground p-0.5 rounded-full shadow-sm">
                          <AlertCircle className="w-3 h-3" />
                        </div>
                      )}
                    </div>
                  </Card>

                  {/* Connecting Line to next node */}
                  {!isLast && (
                    <div className="absolute top-1/2 -right-12 w-12 h-0.5 bg-white/5 overflow-hidden hidden xl:block text-center flex items-center justify-center">
                      {(node.status === 'done' || node.status === 'running') && (
                        <motion.div 
                          className="h-full bg-[#7A8D7A] w-full"
                          initial={{ x: "-100%" }}
                          animate={{ x: "0%" }}
                          transition={{ duration: 0.5, ease: "easeOut" }}
                        />
                      )}
                    </div>
                  )}
                </motion.div>
                
                {/* Visual arrow for mobile/wrap */}
                {!isLast && (
                  <ChevronRight className="w-4 h-4 text-muted-foreground/30 xl:hidden mx-2 mt-4" />
                )}
              </div>
            );
          })}
        </div>

        {/* Dynamic Scrapers Grid */}
        <AnimatePresence>
          {scraperNodes.length > 0 && (
            <motion.div 
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex flex-col items-center gap-4 border-t pt-8 w-full"
            >
              <div className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground flex items-center gap-2">
                <Search className="w-3 h-3" /> Active Data Scrapers
              </div>
              <div className="flex flex-wrap justify-center gap-3">
                {scraperNodes.map((node) => (
                  <motion.div
                    layout
                    key={node.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <Badge variant="secondary" className="px-3 py-1.5 flex items-center gap-2 bg-card border hover:border-primary/50 cursor-pointer transition-colors" onClick={() => onNodeClick(node.id)}>
                      <span className={`w-1.5 h-1.5 rounded-full ${node.status === 'running' ? 'bg-primary animate-pulse' : 'bg-emerald-500'}`} />
                      <span className="font-semibold text-[11px] truncate max-w-[100px]">{node.label}</span>
                    </Badge>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="mt-12 flex gap-8 text-[10px] text-muted-foreground font-semibold uppercase tracking-widest bg-card border rounded-full px-6 py-2 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-slate-400" /> Pending
        </div>
         <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary" /> Active
        </div>
         <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500" /> Complete
        </div>
      </div>
    </div>
  );
}
