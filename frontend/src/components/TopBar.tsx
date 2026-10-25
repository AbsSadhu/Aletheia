import { useState } from "react";
import { Moon, Plus, RefreshCw, Sun } from "lucide-react";
import { resolveTheme, setTheme } from "../lib/theme";
import type { Theme } from "../lib/theme";

interface TopBarProps {
  title: string;
  onNewRun?: () => void;
  onRefresh?: () => void;
  loading?: boolean;
}

export default function TopBar({ title, onNewRun, onRefresh, loading }: TopBarProps) {
  const [theme, setThemeState] = useState<Theme>(() => resolveTheme());
  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    setThemeState(next);
  };
  return (
    <header className="topbar">
      <h1 className="topbar-title">{title}</h1>
      <div className="topbar-actions">
        <button
          className="btn btn-ghost"
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        {onRefresh && (
          <button
            className="btn btn-ghost"
            onClick={onRefresh}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? "pulse" : ""} />
          </button>
        )}
        {onNewRun && (
          <button
            className="btn btn-primary"
            onClick={onNewRun}
            disabled={loading}
          >
            <Plus size={16} />
            New Analysis
          </button>
        )}
      </div>
    </header>
  );
}
