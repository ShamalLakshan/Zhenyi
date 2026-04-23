import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip as ChartTooltip, 
  ResponsiveContainer,
  Cell
} from 'recharts';
import { Copy, Check, Clock, ShieldCheck, Share2, MessageSquare, Activity } from "lucide-react";
import { useState } from "react";
import { motion } from "motion/react";

interface ResultPanelProps {
  answer: string;
  confidence: number;
  profile: string;
  duration: number;
  query: string;
}

export function ResultPanel({ answer, confidence, profile, duration, query }: ResultPanelProps) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const confidenceColor = confidence > 0.8 ? 'text-emerald-500' : confidence > 0.6 ? 'text-amber-500' : 'text-red-500';

  // Mock data for timing based on total duration
  const chartData = [
    { name: 'Planning', value: duration * 0.1 },
    { name: 'Scraping', value: duration * 0.4 },
    { name: 'Triage', value: duration * 0.2 },
    { name: 'Analyst', value: duration * 0.2 },
    { name: 'Synthesis', value: duration * 0.1 },
  ];

  const COLORS = ['#7A8D7A66', '#7A8D7A99', '#7A8D7ACC', '#7A8D7AFF', '#7A8D7A33'];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-hidden flex flex-col max-w-4xl mx-auto w-full p-8 gap-8">
        
        {/* User Query Bubble */}
        <div className="flex gap-4">
          <div className="w-8 h-8 rounded-full bg-secondary shrink-0 flex items-center justify-center text-[10px] border border-white/10 text-muted-foreground uppercase font-bold">User</div>
          <div className="glass p-4 rounded-2xl rounded-tl-none text-sm leading-relaxed max-w-[85%] font-medium">
            {query}
          </div>
        </div>

        {/* Agent Answer Card */}
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex-1 min-h-0 flex flex-col gap-6"
        >
          <div className="flex gap-4 h-full">
            <div className="w-8 h-8 rounded-full bg-primary shrink-0 flex items-center justify-center text-[10px] text-white font-bold uppercase ring-4 ring-primary/10">ZY</div>
            <Card className="glass flex flex-col flex-1 min-h-0 border-none shadow-2xl overflow-hidden rounded-2xl rounded-tl-none bg-muted/40 border-l-4 border-l-primary backdrop-blur-xl">
              <CardHeader className="border-b border-white/5 py-4 px-6 flex flex-row items-center justify-between space-y-0">
                 <div className="flex items-center gap-2">
                   <ShieldCheck className="w-5 h-5 text-primary" />
                   <CardTitle className="text-sm font-bold uppercase tracking-widest text-[#7A8D7A]">Synthesized Intelligence</CardTitle>
                 </div>
                 <div className="flex items-center gap-6">
                   <div className="text-right">
                     <p className="text-[9px] uppercase font-bold text-white/40 mb-0.5 tracking-tight">Confidence Score</p>
                     <p className={`text-xl font-light tracking-tight ${(confidence > 0.8 ? 'text-primary' : 'text-amber-500')}`}>{(confidence * 100).toFixed(1)}%</p>
                   </div>
                   <Badge variant="outline" className="font-bold text-[10px] bg-white/5 border-white/10 uppercase tracking-widest">{profile}</Badge>
                 </div>
              </CardHeader>
              <CardContent className="flex-1 overflow-hidden p-0 flex flex-col">
                <ScrollArea className="flex-1">
                  <div className="p-8 prose prose-slate dark:prose-invert max-w-none prose-sm leading-relaxed text-slate-300">
                    {answer.split('\n\n').map((para, i) => (
                      <p key={i} className="mb-4 last:mb-0">
                        {para}
                      </p>
                    ))}
                  </div>
                </ScrollArea>
                
                {/* Performance Metrics Chart */}
                <div className="h-32 px-8 pt-4 border-t border-white/5 bg-white/2">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-3.5 h-3.5 text-primary opacity-50" />
                    <span className="text-[10px] font-bold uppercase text-primary tracking-widest opacity-60">Synthesis Metrics</span>
                  </div>
                  <ResponsiveContainer width="100%" height="70%">
                    <BarChart data={chartData} margin={{ top: 0, right: 0, left: -40, bottom: 0 }}>
                      <XAxis 
                         dataKey="name" 
                         fontSize={8} 
                         tickLine={false} 
                         axisLine={false}
                         stroke="rgba(255,255,255,0.2)"
                         className="serif"
                      />
                      <YAxis hide />
                      <ChartTooltip 
                        contentStyle={{ 
                          fontSize: '10px', 
                          borderRadius: '12px', 
                          border: '1px solid rgba(255,255,255,0.1)', 
                          boxShadow: '0 8px 16px rgba(0,0,0,0.5)',
                          backgroundColor: '#151815',
                          color: '#E4E7E4'
                        }} 
                      />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={35}>
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
              <CardFooter className="border-t border-white/5 px-6 py-4 flex items-center justify-between bg-white/2">
                <div className="flex items-center gap-6 text-[10px] text-white/30 font-bold uppercase tracking-widest">
                  <span className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-primary" />
                    {(duration / 1000).toFixed(2)}s process
                  </span>
                  <span className="flex items-center gap-2">
                    <MessageSquare className="w-3.5 h-3.5 text-primary" />
                    Verified Citation
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" className="h-8 gap-2 font-bold text-[10px] uppercase border border-white/10 hover:bg-white/5" onClick={copyToClipboard}>
                    {copied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                    {copied ? 'Copied' : 'Copy'}
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-white/5">
                     <Share2 className="w-3.5 h-3.5 opacity-50" />
                  </Button>
                </div>
              </CardFooter>
            </Card>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
