import { Moon, Sun, Search, Zap, History, Settings } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

interface HeaderProps {
  status: string;
  onToggleHistory: () => void;
}

export function Header({ status, onToggleHistory }: HeaderProps) {
  const { theme, setTheme } = useTheme();

  return (
    <header className="fixed top-0 left-0 right-0 h-16 border-b bg-background/80 backdrop-blur-md z-50 flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
          <Zap className="w-5 h-5 text-primary-foreground" />
        </div>
        <div>
          <h1 className="font-bold text-lg tracking-tight">Zhenyi</h1>
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold -mt-1">Research Agent</p>
        </div>
        <Badge variant="outline" className="ml-4 flex items-center gap-1.5 py-1 px-3 border-primary/30 bg-primary/5">
          <span className={`w-2 h-2 rounded-full ${
            status === 'running' ? 'bg-[#7A8D7A] animate-pulse' : 
            status === 'done' ? 'bg-[#7A8D7A]' : 'bg-slate-400/30'
          }`} />
          <span className="text-[10px] uppercase font-bold tracking-widest text-primary leading-none">{status}</span>
        </Badge>
      </div>

      <div className="flex items-center gap-2">
         <Button variant="ghost" size="icon" onClick={onToggleHistory} className="relative">
          <History className="w-5 h-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </Button>
        <Button variant="ghost" size="icon">
          <Settings className="w-5 h-5" />
        </Button>
      </div>
    </header>
  );
}
