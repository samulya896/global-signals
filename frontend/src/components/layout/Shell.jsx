import { Link, NavLink, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  LayoutDashboard,
  Newspaper,
  Settings2,
  SlidersHorizontal,
  WalletCards,
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
      <header className="masthead">
        <Link className="brand" to="/" aria-label="Global Signals home">
          <span className="brand-symbol" aria-hidden="true">
            G<span>S</span>
          </span>
          <span className="brand-copy">
            <b>GLOBAL SIGNALS</b>
            <small>MARKET RESEARCH</small>
          </span>
        </Link>
        <div className="masthead-center">
          <span className="workspace-label">PERSONAL WORKSPACE</span>
          <span className="environment-status">
            <span className="status-dot" />
            Paper environment
          </span>
        </div>
        <div className="masthead-actions">
          <div className="masthead-quote" aria-label="Latest available quote">
            <span>{spy?.provider ?? "Market data"}</span>
            {spy
              ? `${spy.symbol} ${quoteAmount(spy.price, spy.quote_currency ?? spy.currency ?? "INR")}`
              : "Quotes loading"}
          </div>
          <span className="user-email" title={user.email}>
            {user.email}
          </span>
          <button className="logout-button" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>
      <div className="navigation-band">
        <nav className="workspace-nav" aria-label="Main navigation">
          {nav.map(({ label, to, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active" : ""}`
              }
            >
              <Icon aria-hidden="true" size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <span className="navigation-context">
          <span className="status-dot" />
          Virtual orders only
        </span>
      </div>
      <div className="main-column">
        <main key={location.pathname} className="content page-transition">
          <div className="page-context" aria-label="Current location">
            <span>WORKSPACE</span>
            <span className="context-separator">/</span>
            <strong>{currentPage}</strong>
          </div>
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
