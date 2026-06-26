import { Plus, RefreshCw } from "lucide-react";

interface TopBarProps {
  title: string;
  onNewRun?: () => void;
  onRefresh?: () => void;
  loading?: boolean;
}

export default function TopBar({ title, onNewRun, onRefresh, loading }: TopBarProps) {
  return (
    <header className="topbar">
      <h1 className="topbar-title">{title}</h1>
      <div className="topbar-actions">
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
