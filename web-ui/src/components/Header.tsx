import { Moon, Sun, Zap, History, Settings } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

interface HeaderProps {
  status: string;
  onToggleHistory: () => void;
  selectedStageId?: string | null;
  uiScale: number;
  onUiScaleChange: (next: number) => void;
}

export function Header({ status, onToggleHistory, selectedStageId, uiScale, onUiScaleChange }: HeaderProps) {
  const { theme, setTheme } = useTheme();

  return (
    <header className="h-14 border-b border-border bg-[#0c0c0e]/80 backdrop-blur-md flex items-center justify-between px-6 shrink-0 relative z-50">
      <div className="flex items-center gap-4">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center shadow-lg shadow-primary/20">
          <Zap className="w-5 h-5 text-white" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-bold tracking-tight">Zhenyi</span>
          <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-[0.2em]">Research Agent</span>
        </div>
        <Badge variant="outline" className="ml-4 flex items-center gap-2 py-1 px-3 bg-zinc-900 border-zinc-800 rounded-full">
          <span className={`w-1.5 h-1.5 rounded-full ${
            status === 'running' ? 'bg-primary animate-pulse' : 
            status === 'done' ? 'bg-emerald-500' : 'bg-zinc-700'
          }`} />
          <span className="text-[10px] font-bold text-zinc-400 capitalize">{status}</span>
        </Badge>
      </div>

      <div className="flex items-center gap-3">
        <Badge variant="outline" className="h-8 px-3 bg-zinc-900 border-zinc-800 text-[10px] uppercase tracking-[0.16em] font-black text-zinc-300">
          {selectedStageId ? `Stage: ${selectedStageId}` : "Overview"}
        </Badge>
        <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-xl border border-zinc-800 bg-zinc-900">
          <span className="text-[9px] uppercase tracking-[0.18em] font-black text-zinc-500">UI Scale</span>
          <input
            type="range"
            min={88}
            max={100}
            value={Math.round(uiScale * 100)}
            onChange={(e) => onUiScaleChange(Number(e.target.value) / 100)}
            className="w-24 accent-primary"
          />
        </div>
        <button 
           onClick={onToggleHistory}
           className="px-4 py-1.5 bg-primary hover:bg-primary/90 text-white rounded text-xs font-bold transition-all"
        >
          View Archive
        </button>
        <Button
          variant="ghost"
          size="icon"
          className="rounded-xl hover:bg-zinc-800"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </Button>
      </div>
    </header>
  );
}
