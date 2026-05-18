import React, { useState } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Sparkles, Zap } from "lucide-react";
import { motion } from "motion/react";

interface QueryInputProps {
  onSubmit: (query: string, focusArea?: string, llmRatio?: number, scraperRatio?: number) => void;
  isLoading: boolean;
}

export function QueryInput({ onSubmit, isLoading }: QueryInputProps) {
  const [query, setQuery] = useState("");
  const [llmRatio, setLlmRatio] = useState(70);
  const [scraperRatio, setScraperRatio] = useState(30);

  const syncLlmRatio = (value: number) => {
    const normalized = Math.max(0, Math.min(100, value));
    setLlmRatio(normalized);
    setScraperRatio(100 - normalized);
  };

  const syncScraperRatio = (value: number) => {
    const normalized = Math.max(0, Math.min(100, value));
    setScraperRatio(normalized);
    setLlmRatio(100 - normalized);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSubmit(query, undefined, llmRatio, scraperRatio);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col h-full items-center justify-center p-8"
    >
      <Card className="w-full max-w-xl bg-zinc-900 border-zinc-800 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 p-4 opacity-10">
          <Sparkles className="w-12 h-12" />
        </div>
        <CardHeader className="space-y-1 text-center py-10">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-2xl bg-primary flex items-center justify-center shadow-2xl shadow-primary/20 transform -rotate-3">
              <Zap className="w-8 h-8 text-white" />
            </div>
          </div>
          <CardTitle className="text-3xl font-black tracking-tighter">Zhenyi</CardTitle>
          <CardDescription className="text-[10px] font-black text-zinc-500 uppercase tracking-[0.3em]">
            Research Agent
          </CardDescription>
        </CardHeader>
        <CardContent className="px-10 pb-10">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="relative group p-1 bg-zinc-950 border border-zinc-800 rounded-2xl focus-within:border-primary/50 transition-all">
              <Textarea
                placeholder="Ask a research question..."
                className="min-h-35 bg-transparent border-none text-sm resize-none focus-visible:ring-0 placeholder:text-zinc-700 p-4 font-medium"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isLoading}
              />
              <div className="flex justify-end p-2 border-t border-zinc-900">
                <Button
                  type="submit"
                  className="rounded-xl px-6 h-10 font-black uppercase tracking-widest text-[10px] shadow-lg shadow-primary/20"
                  disabled={isLoading || !query.trim()}
                >
                  {isLoading ? (
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    "Search"
                  )}
                </Button>
              </div>
            </div>

            <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.25em] text-zinc-500">Execution Ratio</p>
                  <p className="text-[11px] text-zinc-400 mt-1">Shift the balance before the query starts</p>
                </div>
                <div className="text-right text-[10px] font-black uppercase tracking-[0.25em] text-zinc-400">
                  <div>LLM {llmRatio}%</div>
                  <div>Scraper {scraperRatio}%</div>
                </div>
              </div>

              <div className="space-y-3">
                <label className="block text-[9px] font-black uppercase tracking-[0.25em] text-zinc-500">
                  LLM Share
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={llmRatio}
                  onChange={(e) => syncLlmRatio(Number(e.target.value))}
                  className="w-full accent-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="space-y-2">
                  <span className="block text-[9px] font-black uppercase tracking-[0.25em] text-zinc-500">LLM %</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={llmRatio}
                    onChange={(e) => syncLlmRatio(Number(e.target.value || 0))}
                    className="w-full h-10 rounded-xl border border-zinc-800 bg-zinc-950 px-3 text-sm outline-none focus:border-primary/50"
                  />
                </label>
                <label className="space-y-2">
                  <span className="block text-[9px] font-black uppercase tracking-[0.25em] text-zinc-500">Scraper %</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={scraperRatio}
                    onChange={(e) => syncScraperRatio(Number(e.target.value || 0))}
                    className="w-full h-10 rounded-xl border border-zinc-800 bg-zinc-950 px-3 text-sm outline-none focus:border-primary/50"
                  />
                </label>
              </div>
            </div>
          </form>
        </CardContent>
      </Card>
      
      <div className="grid grid-cols-2 gap-3 mt-12 max-w-xl w-full">
        {[
          { label: "Multiple Sources", desc: "Scrapers & AI Models", color: "indigo" },
          { label: "Fast Results", desc: "Streaming Response", color: "emerald" },
        ].map((item, i) => (
          <div key={i} className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/50 flex flex-col gap-1 shadow-sm">
            <div className="flex items-center gap-2 mb-1">
               <div className={`w-2 h-2 rounded-full bg-${item.color}-500`} />
               <span className="text-[9px] font-black uppercase text-zinc-600 tracking-widest">{item.label}</span>
            </div>
            <p className="text-xs font-bold tracking-tight">{item.desc}</p>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
