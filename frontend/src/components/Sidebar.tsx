import { useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Activity,
  Briefcase,
  FlaskConical,
  Ghost,
  LayoutDashboard,
  Lightbulb,
  LineChart,
  Network,
  Newspaper,
  NotebookPen,
  Pin,
  PinOff,
  Play,
  Radio,
  Settings,
  ShieldCheck,
  Sigma,
  TrendingUp,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";

import RouterLink from "./RouterLink";

interface NavItem {
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
}

/** Sections shown in the side navigation. */
export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview",
    items: [
      { to: "/", icon: LayoutDashboard, label: "Dashboard" },
      { to: "/runs", icon: Play, label: "Runs" },
    ],
  },
  {
    title: "Markets",
    items: [
      { to: "/live", icon: Radio, label: "Live Market" },
      { to: "/pulse", icon: Newspaper, label: "Market Pulse" },
      { to: "/correlation", icon: Network, label: "Correlation" },
      { to: "/options", icon: Sigma, label: "Options" },
      { to: "/factors", icon: FlaskConical, label: "Factor Explorer" },
    ],
  },
  {
    title: "Trading",
    items: [
      { to: "/portfolio", icon: Briefcase, label: "Portfolio" },
      { to: "/paper-trades", icon: TrendingUp, label: "Paper Trades" },
      { to: "/shadow-trader", icon: Ghost, label: "Shadow Trader" },
      { to: "/backtest", icon: LineChart, label: "Backtest" },
      { to: "/journal", icon: NotebookPen, label: "Trade Journal" },
    ],
  },
  {
    title: "Research",
    items: [
      { to: "/hypotheses", icon: Lightbulb, label: "Hypotheses" },
      { to: "/validation", icon: ShieldCheck, label: "Signal Validation" },
    ],
  },
  {
    title: "System",
    items: [{ to: "/settings", icon: Settings, label: "Settings" }],
  },
];

/** Flat list, for the command menu. */
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

interface SidebarProps {
  backendOnline: boolean;
}

const PIN_KEY = "aletheia_rail_pinned";

function readPinned(): boolean {
  try {
    return localStorage.getItem(PIN_KEY) === "1";
  } catch {
    return false;
  }
}

function isCurrent(pathname: string, to: string): boolean {
  return to === "/" ? pathname === "/" : pathname === to || pathname.startsWith(`${to}/`);
}

/** A small cube that turns slowly: red front, orange sides. Pure CSS 3D. */
function BrandCube() {
  return (
    <span className="cube-stage" aria-hidden="true">
      <span className="cube">
        <i className="f1">A</i>
        <i className="f2" />
        <i className="f3">λ</i>
        <i className="f4" />
        <i className="f5" />
        <i className="f6" />
      </span>
    </span>
  );
}

/**
 * The side rail. Collapsed it is a column of icon keys; hovering or focusing into it opens the
 * labelled panel over the page, and the pin keeps it open. The current page is a raised red key.
 */
export default function Sidebar({ backendOnline }: SidebarProps) {
  const { pathname } = useLocation();
  const [pinned, setPinned] = useState(readPinned);
  const togglePin = () => {
    setPinned((p) => {
      try {
        localStorage.setItem(PIN_KEY, p ? "0" : "1");
      } catch {
        /* storage unavailable: the pin lasts for this session */
      }
      return !p;
    });
  };

  let n = 0;
  return (
    <div className="sidebar-slot" data-pinned={pinned ? "true" : "false"}>
      <nav className="rail" aria-label="Primary">
        <RouterLink href="/" className="rail-brand" aria-label="Aletheia home">
          <BrandCube />
          <span className="rail-word">ALETHEIA</span>
        </RouterLink>

        <div className="rail-scroll">
          {NAV_GROUPS.map((group) => (
            <div className="rail-group" key={group.title}>
              <div className="rail-group-title">{group.title}</div>
              {group.items.map((item) => {
                const current = isCurrent(pathname, item.to);
                const Icon = item.icon;
                return (
                  <RouterLink
                    key={item.to}
                    href={item.to}
                    className={`rail-item${current ? " active" : ""}`}
                    aria-current={current ? "page" : undefined}
                    style={{ ["--n" as string]: n++ } as React.CSSProperties}
                  >
                    <span className="rail-icon">
                      <Icon width={19} height={19} aria-hidden="true" />
                    </span>
                    <span className="rail-label">{item.label}</span>
                  </RouterLink>
                );
              })}
            </div>
          ))}
        </div>

        <div className="rail-foot">
          <div className="rail-status" title={backendOnline ? "Backend connected" : "Backend offline"}>
            <span className={`status-dot${backendOnline ? "" : " offline"}`} />
            <span className="rail-label">{backendOnline ? "Backend connected" : "Backend offline"}</span>
          </div>
          <div className="rail-status">
            <Activity size={14} aria-hidden="true" />
            <span className="rail-label">
              v{__APP_VERSION__} · alpha
            </span>
          </div>
          <button
            type="button"
            className="rail-pin"
            onClick={togglePin}
            aria-pressed={pinned}
            aria-label={pinned ? "Unpin side rail" : "Pin side rail open"}
            title={pinned ? "Unpin" : "Keep open"}
          >
            {pinned ? <PinOff size={15} /> : <Pin size={15} />}
          </button>
        </div>
      </nav>
    </div>
  );
}
