import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Play,
  Briefcase,
  Settings,
  Activity,
  TrendingUp,
  FlaskConical,
  Ghost,
  LineChart,
  Lightbulb,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/runs", icon: Play, label: "Runs" },
  { to: "/portfolio", icon: Briefcase, label: "Portfolio" },
  { to: "/paper-trades", icon: TrendingUp, label: "Paper Trades" },
  { to: "/shadow-trader", icon: Ghost, label: "Shadow Trader" },
  { to: "/backtest", icon: LineChart, label: "Backtest" },
  { to: "/hypotheses", icon: Lightbulb, label: "Hypotheses" },
  { to: "/factors", icon: FlaskConical, label: "Factor Explorer" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

interface SidebarProps {
  backendOnline: boolean;
}

export default function Sidebar({ backendOnline }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">Aλ</div>
        <span className="sidebar-brand-name">ALETHEIA</span>
      </div>

      <div className="sidebar-section-label">Navigation</div>
      <nav>
        <ul className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `sidebar-link${isActive ? " active" : ""}`
                }
              >
                <item.icon />
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-status">
          <span className={`status-dot${backendOnline ? "" : " offline"}`} />
          <span>
            {backendOnline ? "Backend connected" : "Backend offline"}
          </span>
        </div>
        <div className="sidebar-status" style={{ marginTop: 6 }}>
          <Activity size={12} />
          <span>v0.1.0 · Sprint 3</span>
        </div>
      </div>
    </aside>
  );
}
