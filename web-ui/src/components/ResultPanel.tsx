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
import { Copy, Check, Clock, ShieldCheck, MessageSquare, Activity } from "lucide-react";
import { useState } from "react";
import { motion } from "motion/react";
import type { StageBreakdownItem, UsageEntry } from "../lib/api";

interface ResultPanelProps {
  answer: string;
  confidence: number;
  profile: string;
  duration: number;
  query: string;
  stageBreakdown?: StageBreakdownItem[];
  providerUsage?: UsageEntry[];
  scraperUsage?: UsageEntry[];
  sources?: string[];
  ratioControls?: {
    llm_ratio?: number;
    scraper_ratio?: number;
  };
  ratioMetrics?: {
    requested_llm_ratio?: number;
    requested_scraper_ratio?: number;
    achieved_llm_ratio?: number;
    achieved_scraper_ratio?: number;
    deviation_reason?: string;
  };
}

export function ResultPanel({
  answer,
  confidence,
  profile,
  duration,
  query,
  stageBreakdown,
  providerUsage,
  scraperUsage,
  sources,
  ratioControls,
  ratioMetrics,
}: ResultPanelProps) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const chartData =
    stageBreakdown && stageBreakdown.length > 0
      ? stageBreakdown
      : [
          { name: 'Plan', value: 0, usage_pct: 0 },
          { name: 'Crawl', value: 0, usage_pct: 0 },
          { name: 'Triage', value: 0, usage_pct: 0 },
          { name: 'Analyst', value: 0, usage_pct: 0 },
          { name: 'Synth', value: 0, usage_pct: 0 },
        ];

  const topProviders = (providerUsage || []).slice(0, 3);
  const topScrapers = (scraperUsage || []).slice(0, 3);

  const COLORS = ['#94a3b8', '#64748b', '#475569', 'var(--color-primary)', '#334155'];

  return (
    <div className="flex flex-col h-full bg-zinc-950/20">
      <div className="flex-1 overflow-hidden flex flex-col max-w-none mx-auto w-full p-4 xl:p-6 gap-5">
        
        {/* User Query Bubble */}
        <div className="flex gap-4">
          <div className="w-8 h-8 rounded bg-zinc-800 shrink-0 flex items-center justify-center text-[9px] border border-zinc-700 text-zinc-500 uppercase font-black">User</div>
          <div className="p-4 rounded-2xl rounded-tl-none bg-zinc-900 border border-zinc-800 text-xs leading-relaxed max-w-[85%] font-medium shadow-sm text-zinc-300">
            {query}
          </div>
        </div>

        {/* Agent Answer Card */}
        <motion.div 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex-1 min-h-0 flex flex-col gap-6"
        >
          {(ratioControls || ratioMetrics) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
                <p className="text-[9px] font-black uppercase tracking-[0.25em] text-zinc-500 mb-2">Requested Ratio</p>
                <div className="flex items-center justify-between text-sm font-bold text-zinc-200">
                  <span>LLM {ratioControls?.llm_ratio ?? ratioMetrics?.requested_llm_ratio ?? 0}%</span>
                  <span>Scraper {ratioControls?.scraper_ratio ?? ratioMetrics?.requested_scraper_ratio ?? 0}%</span>
                </div>
              </div>
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
                <p className="text-[9px] font-black uppercase tracking-[0.25em] text-zinc-500 mb-2">Achieved Ratio</p>
                <div className="flex items-center justify-between text-sm font-bold text-zinc-200">
                  <span>LLM {ratioMetrics?.achieved_llm_ratio ?? 0}%</span>
                  <span>Scraper {ratioMetrics?.achieved_scraper_ratio ?? 0}%</span>
                </div>
                {ratioMetrics?.deviation_reason && (
                  <p className="mt-2 text-[10px] text-zinc-500 uppercase tracking-widest">{ratioMetrics.deviation_reason}</p>
                )}
              </div>
            </div>
          )}

          <div className="flex gap-4 h-full relative">
            <div className="w-8 h-8 rounded bg-primary shrink-0 flex items-center justify-center text-[9px] text-white font-black uppercase shadow-lg shadow-primary/20">ZY</div>
            <Card className="flex flex-col flex-1 min-h-0 border-zinc-800 shadow-2xl overflow-hidden rounded-2xl rounded-tl-none bg-zinc-900/50 backdrop-blur-3xl">
              <CardHeader className="border-b border-zinc-800 py-3 px-6 flex flex-row items-center justify-between space-y-0 bg-[#0c0c0e]">
                 <div className="flex items-center gap-2">
                   <ShieldCheck className="w-4 h-4 text-primary" />
                   <CardTitle className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">Research Result</CardTitle>
                 </div>
                 <div className="flex items-center gap-10">
                   <div className="text-right">
                     <p className="text-[8px] uppercase font-black text-zinc-600 mb-0.5 tracking-widest">Reliability Score</p>
                     <p className={`text-xl font-black tracking-tighter ${(confidence > 0.8 ? 'text-emerald-500' : 'text-amber-500')}`}>{(confidence * 100).toFixed(1)}%</p>
                   </div>
                   <Badge variant="outline" className="font-black text-[9px] bg-zinc-800 border-zinc-700 uppercase tracking-widest px-3 h-6 rounded-md">{profile}</Badge>
                 </div>
              </CardHeader>
              <CardContent className="flex-1 overflow-hidden p-0 flex flex-col">
                <ScrollArea className="flex-1">
                  <div className="p-6 xl:p-8 prose prose-slate dark:prose-invert max-w-none text-[15px] leading-relaxed text-foreground/90">
                    {answer.split('\n\n').map((para, i) => (
                      <p key={i} className="mb-6 last:mb-0">
                        {para}
                      </p>
                    ))}
                  </div>
                </ScrollArea>
                
                {/* Performance Metrics Chart */}
                <div className="h-34 px-6 xl:px-8 pt-4 border-t border-zinc-800 bg-[#0c0c0e]/30">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-3.5 h-3.5 text-primary opacity-50" />
                    <span className="text-[9px] font-black uppercase text-zinc-600 tracking-widest">Stage Latency (ms)</span>
                  </div>
                  <ResponsiveContainer width="100%" height="70%">
                    <BarChart data={chartData} margin={{ top: 0, right: 0, left: -45, bottom: 0 }}>
                      <XAxis 
                         dataKey="name" 
                         fontSize={9} 
                         tickLine={false} 
                         axisLine={false}
                         stroke="var(--color-zinc-700)"
                      />
                      <YAxis hide />
                      <ChartTooltip 
                        cursor={{ fill: 'transparent' }}
                        formatter={(value: number, _name: string, payload: any) => [
                          `${Number(value).toFixed(0)} ms (${payload?.payload?.usage_pct ?? 0}%)`,
                          payload?.payload?.name || 'Stage',
                        ]}
                        contentStyle={{ 
                          fontSize: '11px', 
                          borderRadius: '8px', 
                          border: '1px solid var(--color-zinc-800)', 
                          backgroundColor: '#09090b',
                          color: '#f4f4f5'
                        }} 
                      />
                      <Bar dataKey="value" radius={[2, 2, 0, 0]} barSize={40}>
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="px-6 xl:px-8 pb-5 border-t border-zinc-800 bg-[#0c0c0e]/10 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <p className="text-[9px] font-black uppercase text-zinc-600 tracking-widest mb-2">Top LLM Usage</p>
                    <div className="space-y-1.5">
                      {topProviders.length > 0 ? topProviders.map((p) => (
                        <div key={p.provider || p.name} className="text-[10px] text-zinc-300 flex items-center justify-between">
                          <span className="truncate pr-2">{p.provider || p.name}</span>
                          <span className="font-bold text-primary">{p.usage_pct.toFixed(1)}%</span>
                        </div>
                      )) : <p className="text-[10px] text-zinc-500">Awaiting model usage data</p>}
                    </div>
                  </div>
                  <div>
                    <p className="text-[9px] font-black uppercase text-zinc-600 tracking-widest mb-2">Top Scraper Usage</p>
                    <div className="space-y-1.5">
                      {topScrapers.length > 0 ? topScrapers.map((s) => (
                        <div key={s.name || s.provider} className="text-[10px] text-zinc-300 flex items-center justify-between">
                          <span className="truncate pr-2">{s.name || s.provider}</span>
                          <span className="font-bold text-emerald-400">{s.usage_pct.toFixed(1)}%</span>
                        </div>
                      )) : <p className="text-[10px] text-zinc-500">Awaiting scraper usage data</p>}
                    </div>
                  </div>
                  <div>
                    <p className="text-[9px] font-black uppercase text-zinc-600 tracking-widest mb-2">Sources</p>
                    <div className="space-y-1.5 max-h-16 overflow-y-auto pr-1">
                      {(sources || []).length > 0 ? (sources || []).slice(0, 5).map((src, i) => (
                        <p key={`${src}-${i}`} className="text-[10px] text-zinc-400 truncate">{src}</p>
                      )) : <p className="text-[10px] text-zinc-500">No source URLs recorded</p>}
                    </div>
                  </div>
                </div>
              </CardContent>
              <CardFooter className="border-t border-zinc-800 px-6 py-4 flex items-center justify-between bg-[#0c0c0e]">
                <div className="flex items-center gap-6 text-[9px] text-zinc-600 font-black uppercase tracking-widest">
                  <span className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-primary/60" />
                    {(duration / 1000).toFixed(2)}s execution
                  </span>
                  <span className="flex items-center gap-2">
                    <MessageSquare className="w-3.5 h-3.5 text-primary/60" />
                    Query Complete
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" className="h-8 gap-2 font-black text-[9px] uppercase border-zinc-800 bg-zinc-900" onClick={copyToClipboard}>
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                    {copied ? 'Captured' : 'Copy'}
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
