import { useState } from "react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  ChevronDown,
  LayoutDashboard,
  Menu,
  Newspaper,
  Settings2,
  SlidersHorizontal,
  WalletCards,
  X,
} from "lucide-react";
import { api } from "../../lib/api";
import type { AuthUser, Quote } from "../../lib/api";
import { quoteAmount } from "../../lib/formatters";

const nav = [
  { label: "Overview", to: "/", icon: LayoutDashboard },
  { label: "News terminal", to: "/news", icon: Newspaper },
  { label: "Market watch", to: "/markets", icon: Activity },
  { label: "Paper trading", to: "/paper", icon: WalletCards },
  { label: "Strategy lab", to: "/strategy", icon: SlidersHorizontal },
  { label: "Backtesting", to: "/backtest", icon: BarChart3 },
  { label: "Settings", to: "/settings", icon: Settings2 },
];

export function Shell({
  user,
  onLogout,
  children,
}: {
  user: AuthUser;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const market = useQuery({
    queryKey: ["market"],
    queryFn: () => api<Quote[]>("/api/v1/market"),
  });
  const spy = market.data?.[0];

  return (
    <div className="app-frame">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-symbol">
            G<span>.</span>
          </div>
          <div>
            <b>GLOBAL SIGNALS</b>
            <small>MARKET INTELLIGENCE</small>
          </div>
          <button
            className="icon-button close-nav"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X size={17} />
          </button>
        </div>
        <div className="workspace">
          <span className="workspace-icon">
            <BriefcaseBusiness size={15} />
          </span>
          <div>
            <b>Paper portfolio</b>
            <small>Personal workspace</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          {nav.map(({ label, to, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection">
            <span className="status-dot" />
            <div>
              <b>SIMULATION MODE</b>
              <small>Orders are virtual only</small>
            </div>
          </div>
          <div className="user-row">
            <div className="avatar">{user.email.slice(0, 2).toUpperCase()}</div>
            <div>
              <b>{user.email}</b>
              <small>Personal paper account</small>
            </div>
            <button className="logout-button" onClick={onLogout}>
              Sign out
            </button>
          </div>
        </div>
      </aside>
      {open && <button className="scrim" onClick={() => setOpen(false)} aria-label="Close menu" />}
      <div className="main-column">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={19} />
          </button>
          <div className="crumb">
            <span>Workspace</span>
            <span className="slash">/</span>
            <strong>Market overview</strong>
          </div>
          <div className="top-actions">
            <div className="market-status">
              <span className="status-dot" /> {spy?.provider ?? "Market data"}{" "}
              <span className="top-divider">·</span>{" "}
              {spy
                ? `${spy.symbol} ${quoteAmount(spy.price, spy.quote_currency ?? spy.currency ?? "INR")}`
                : "Quotes loading"}
            </div>
            <div className="top-avatar" aria-label="Local demo account">
              GS
            </div>
          </div>
        </header>
        <main className="content">{children}</main>
        <footer className="footer">
          <span>GLOBAL SIGNALS · LOCAL SIMULATION ENVIRONMENT</span>
          <span>
            Educational use only <span className="footer-dot">●</span> No real orders
          </span>
        </footer>
      </div>
    </div>
  );
}
