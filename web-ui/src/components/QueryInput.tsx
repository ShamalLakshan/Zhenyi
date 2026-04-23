import React, { useState } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Input } from "./ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Play, Sparkles } from "lucide-react";
import { motion } from "motion/react";

interface QueryInputProps {
  onSubmit: (query: string, focusArea?: string) => void;
  isLoading: boolean;
}

export function QueryInput({ onSubmit, isLoading }: QueryInputProps) {
  const [query, setQuery] = useState("");
  const [focusArea, setFocusArea] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSubmit(query, focusArea);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col h-full items-center justify-center p-8"
    >
      <Card className="w-full max-w-xl border-none shadow-2xl bg-card/50 backdrop-blur-sm">
        <CardHeader className="space-y-1 text-center">
          <div className="flex justify-center mb-4">
            <div className="w-12 h-12 rounded-full bg-[#7A8D7A] flex items-center justify-center shadow-lg shadow-[#7A8D7A]/20">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
          </div>
          <CardTitle className="serif text-4xl font-normal text-[#E8E6E1]">Intelligent Research Synthesizer</CardTitle>
          <CardDescription className="text-sm text-foreground/40 max-w-sm mx-auto">
            Analyze complex datasets, generate hypotheses, and cite peer-reviewed sources in real-time.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4 mt-4">
            <div className="p-3 bg-muted/40 rounded-2xl border border-border/50 shadow-inner group focus-within:border-primary/50 transition-all">
              <Textarea
                placeholder="Ask Zhenyi to analyze or search..."
                className="min-h-[100px] bg-transparent border-none text-base resize-none focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-foreground/20"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isLoading}
              />
              <div className="flex justify-end pt-2">
                <Button
                  type="submit"
                  size="icon"
                  className="rounded-xl w-10 h-10 transition-all hover:scale-105 active:scale-95 shadow-lg shadow-primary/20"
                  disabled={isLoading || !query.trim()}
                >
                  {isLoading ? (
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <Play className="w-4 h-4 fill-current" />
                  )}
                </Button>
              </div>
            </div>
          </form>
        </CardContent>
      </Card>
      
      <div className="grid grid-cols-2 gap-4 mt-12 max-w-2xl w-full">
        {[
          { label: "Deep Analysis", desc: "Multi-stage source synthesis" },
          { label: "Rapid Triage", desc: "High-speed filtering & scraping" },
          { label: "Analyst Insight", desc: "Expert-level detail extraction" },
          { label: "Confident Output", desc: "Weighted scoring system" }
        ].map((item, i) => (
          <div key={i} className="p-4 rounded-xl border bg-card/30 backdrop-blur-sm">
            <h4 className="font-bold text-sm mb-1">{item.label}</h4>
            <p className="text-xs text-muted-foreground">{item.desc}</p>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
