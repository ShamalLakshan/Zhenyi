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
  ChevronRight,
  Database
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

export function PipelineFlow({ nodes, onNodeClick }: PipelineFlowProps) {
  // Group nodes
  const coreNodes = nodes.filter(n => !n.id.startsWith('scraper-'));
  const scraperNodes = nodes.filter(n => n.id.startsWith('scraper-'));

  // Positions for nodes for a more "designed" graph look
  const nodePositions: Record<string, { x: number; y: number }> = {
    orchestrator: { x: 0, y: -150 },
    triage: { x: 0, y: 0 },
    analysts: { x: -150, y: 150 },
    synthesizer: { x: 150, y: 150 },
    output: { x: 0, y: 300 }
  };

  return (
    <div className="relative w-full h-[600px] flex items-center justify-center overflow-hidden rounded-3xl border border-dashed border-primary/10 bg-black/5">
      {/* Dynamic Grid Background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-20">
         <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(circle_at_center,var(--color-primary)_1px,transparent_1px)] [background-size:24px_24px]" />
      </div>

      <div className="relative z-10 w-full h-full flex items-center justify-center">
        {/* Connection Lines (SVG) */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="0" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-primary)" opacity="0.3" />
            </marker>
          </defs>
          {/* Simple connections between specific nodes */}
          <path d="M 50% 150 L 50% 300" stroke="var(--color-primary)" strokeWidth="1" strokeDasharray="4 4" opacity="0.2" fill="none" />
        </svg>

        {/* Core Pipeline Nodes */}
        {coreNodes.map((node) => {
          const Icon = (iconMap as any)[node.id] || Zap;
          const pos = nodePositions[node.id] || { x: 0, y: 0 };
          
          return (
            <motion.div
              key={node.id}
              drag
              dragMomentum={false}
              initial={{ ...pos, opacity: 0, scale: 0.8 }}
              animate={{ x: pos.x, y: pos.y, opacity: 1, scale: 1 }}
              whileDrag={{ scale: 1.05, zIndex: 50 }}
              className="absolute cursor-grab active:cursor-grabbing"
            >
              <Card 
                className={`relative w-44 p-4 border transition-all hover:shadow-2xl bg-card/60 backdrop-blur-2xl ${
                  node.status === 'running' ? 'border-primary ring-8 ring-primary/5 shadow-lg shadow-primary/20' : 
                  node.status === 'done' ? 'border-emerald-500/40 bg-emerald-500/5' : 
                  'border-border'
                }`}
                onClick={() => onNodeClick(node.id)}
              >
                <div className="flex flex-col items-center text-center gap-3">
                   <div className={`p-2.5 rounded-xl transition-colors duration-500 ${
                     node.status === 'running' ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/30' :
                     node.status === 'done' ? 'bg-emerald-500 text-white' :
                     'bg-muted text-muted-foreground'
                   }`}>
                     {node.status === 'running' ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />}
                   </div>
                   <div>
                     <h4 className="text-[10px] font-black uppercase tracking-[0.2em] opacity-50 mb-0.5">{node.label}</h4>
                     <p className="text-[11px] font-bold text-foreground line-clamp-1">
                       {node.title || node.subtitle || 'Inactive'}
                     </p>
                   </div>
                </div>
                
                <div className="absolute -top-1.5 -right-1.5 flex items-center justify-center">
                    {node.status === 'done' && (
                      <div className="bg-emerald-500 text-white p-1 rounded-full shadow-lg border-2 border-background">
                        <CheckCircle2 className="w-2.5 h-2.5" />
                      </div>
                    )}
                </div>
              </Card>
            </motion.div>
          );
        })}

        {/* Ingestion Hub (Floating around Triage) */}
        {scraperNodes.length > 0 && (
          <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
            {scraperNodes.map((node, i) => {
              const radius = 220;
              const angle = (i / scraperNodes.length) * Math.PI * 2;
              const x = Math.cos(angle) * radius;
              const y = Math.sin(angle) * radius;

              return (
                <motion.div
                  key={node.id}
                  initial={{ x: 0, y: 0, opacity: 0 }}
                  animate={{ x, y, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 50, damping: 15, delay: i * 0.1 }}
                  className="absolute pointer-events-auto"
                >
                  <Badge variant="outline" className="px-3 py-1.5 bg-card/80 border border-primary/20 shadow-sm backdrop-blur-md flex items-center gap-2 hover:border-primary transition-all">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-[10px] font-black uppercase tracking-tight">{node.label}</span>
                  </Badge>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* Connection Indicator */}
      <div className="absolute bottom-8 left-8 flex items-center gap-3 bg-card/80 border px-4 py-2 rounded-2xl backdrop-blur-md shadow-2xl">
         <div className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
         </div>
         <span className="text-[9px] font-black uppercase tracking-[0.2em] opacity-40">Intelligence Stream Active</span>
      </div>
    </div>
  );
}

