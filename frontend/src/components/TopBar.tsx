import { useEffect, useState } from "react";
import { Bell, MessageSquare, Moon, Plus, RefreshCw, Search, Sun } from "lucide-react";
import { resolveTheme, setTheme } from "../lib/theme";
import type { Theme } from "../lib/theme";
import { toggleChat, useChatOpen } from "../lib/chatPanelStore";
import ModeBadge from "./ModeBadge";
import Flap from "./Flap";
import NewsTape from "./NewsTape";
import SafeLink from "./SafeLink";
import { useNews } from "../lib/newsStore";

function istNow(): string {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
}

interface TopBarProps {
  title: string;
  onNewRun?: () => void;
  onRefresh?: () => void;
  loading?: boolean;
}

export default function TopBar({ title, onNewRun, onRefresh, loading }: TopBarProps) {
  const [theme, setThemeState] = useState<Theme>(() => resolveTheme());
  const chatOpen = useChatOpen();
  const { unread } = useNews();
  const [clock, setClock] = useState(istNow);
  useEffect(() => {
    const id = setInterval(() => setClock(istNow()), 10_000);
    return () => clearInterval(id);
  }, []);
  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    setThemeState(next);
  };
  return (
    <header className="topbar">
      <div className="topbar-row">
      <h1 className="topbar-title">{title}</h1>
      <div className="topbar-actions">
        <span className="topbar-clock" title="India Standard Time">
          <Flap text={clock} hold={false} />
          <span className="topbar-clock-zone">IST</span>
        </span>
        <button
          className="cmd-pill"
          onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }))}
          aria-label="Open command menu"
        >
          <Search size={13} />
          <span>Jump to a page or ask the assistant</span>
          <kbd>CTRL K</kbd>
        </button>
        <SafeLink to="/pulse" className="btn btn-ghost bell" aria-label={unread ? `${unread} new sentiment alerts` : "Sentiment alerts"} title="Sentiment alerts">
          <Bell size={16} />
          {unread > 0 && <span className="bell-n">{unread > 9 ? "9+" : unread}</span>}
        </SafeLink>
        <ModeBadge />
        <button
          className={`btn btn-ghost chat-launch ${chatOpen ? "active" : ""}`}
          onClick={toggleChat}
          title="Assistant (Ctrl+J)"
          aria-label="Toggle assistant"
          aria-pressed={chatOpen}
        >
          <MessageSquare size={16} />
        </button>
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
      </div>
      <NewsTape />
    </header>
  );
}
