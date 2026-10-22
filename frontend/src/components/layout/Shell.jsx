import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  LayoutDashboard,
  Menu,
  Newspaper,
  Settings2,
  SlidersHorizontal,
  WalletCards,
  X,
} from "lucide-react";
import { api } from "../../lib/api";
import { quoteAmount } from "../../lib/formatters";
const nav = [
  { label: "Dashboard", to: "/", icon: LayoutDashboard },
  { label: "Markets", to: "/markets", icon: Activity },
  { label: "News", to: "/news", icon: Newspaper },
  { label: "Paper trading", to: "/paper", icon: WalletCards },
  { label: "Strategy", to: "/strategy", icon: SlidersHorizontal },
  { label: "Backtesting", to: "/backtest", icon: BarChart3 },
  { label: "Settings", to: "/settings", icon: Settings2 },
];
export function Shell({ user, onLogout, children }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const market = useQuery({
    queryKey: ["market"],
    queryFn: () => api("/api/v1/market"),
  });
  const spy = market.data?.[0];
  const currentPage =
    nav.find(({ to }) => to === location.pathname)?.label ?? "Dashboard";
  return (
    <div className="app-frame">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-symbol" aria-hidden="true">
            GS
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
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          {nav.map(({ label, to, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active" : ""}`
              }
            >
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection" aria-label="Paper trading only">
            <span className="status-dot" />
            <div>
              <b>Paper trading</b>
              <small>Virtual orders only</small>
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
      {open && (
        <button
          className="scrim"
          onClick={() => setOpen(false)}
          aria-label="Close menu"
        />
      )}
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
            <strong>{currentPage}</strong>
          </div>
          <div className="top-actions">
            <div className="market-status" aria-label="Latest available quote">
              {spy?.provider ?? "Market data"}{" "}
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
        <main key={location.pathname} className="content page-transition">
          {children}
        </main>
        <footer className="footer">
          <span>GLOBAL SIGNALS · LOCAL SIMULATION ENVIRONMENT</span>
          <span>
            Educational use only <span className="footer-dot">●</span> No real
            orders
          </span>
        </footer>
      </div>
    </div>
  );
}
