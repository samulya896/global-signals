import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowUpRight,
  BriefcaseBusiness,
  Gauge,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import type { Performance, Portfolio, PortfolioPoint, Quote, Signal } from "../lib/api";
import { errorText, money } from "../lib/formatters";
import { ErrorState } from "../components/common/ErrorState";
import { Metric } from "../components/common/Metric";
import { PageTitle } from "../components/common/PageTitle";
import { QuoteTable } from "../components/tables/QuoteTable";
import { SignalList } from "../components/tables/SignalList";
import { TradeTable } from "../components/tables/TradeTable";

export function DashboardPage() {
  const portfolio = useQuery({
    queryKey: ["portfolio"],
    queryFn: () => api<Portfolio>("/api/v1/portfolio"),
  });
  const perf = useQuery({
    queryKey: ["performance"],
    queryFn: () => api<Performance>("/api/v1/performance"),
  });
  const market = useQuery({
    queryKey: ["market"],
    queryFn: () => api<Quote[]>("/api/v1/market"),
  });
  const signals = useQuery({
    queryKey: ["signals"],
    queryFn: () => api<Signal[]>("/api/v1/signals"),
  });
  const history = useQuery({
    queryKey: ["portfolio-history"],
    queryFn: () => api<PortfolioPoint[]>("/api/v1/portfolio/history"),
  });

  const quoteRows = market.data ?? [];

  return (
    <>
      <PageTitle
        eyebrow={
          new Date()
            .toLocaleDateString("en-IN", {
              weekday: "long",
              day: "2-digit",
              month: "long",
              year: "numeric",
            })
            .toUpperCase() + " · PAPER ACCOUNT"
        }
        title="Market overview"
        subtitle="A clear view of your simulated portfolio and the signals behind it."
        action={
          <button
            className="btn btn-secondary"
            onClick={() => {
              void portfolio.refetch();
              void market.refetch();
              void signals.refetch();
              void perf.refetch();
            }}
          >
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <div className="simulation-banner">
        <ShieldCheck size={17} />
        <div>
          <b>Simulation environment</b>
          <span>
            Every order uses virtual funds. No brokerage connection or real trade execution is available.
          </span>
        </div>
        <span className="banner-badge">PAPER ONLY</span>
      </div>
      {portfolio.isError && <ErrorState message={`Portfolio: ${errorText(portfolio.error)}`} />}
      <section className="metrics-grid">
        <Metric
          label="PORTFOLIO EQUITY"
          value={money(portfolio.data?.equity)}
          detail="Virtual cash + marked holdings"
          icon={WalletCards}
          tone="blue"
        />
        <Metric
          label="AVAILABLE CASH"
          value={money(portfolio.data?.cash)}
          detail="Paper buying power"
          icon={Gauge}
        />
        <Metric
          label="INVESTED VALUE"
          value={money(portfolio.data?.market_value)}
          detail="Current simulated market value"
          icon={BriefcaseBusiness}
          tone="purple"
        />
        <Metric
          label="TOTAL RETURN"
          value={`${(perf.data?.total_return ?? 0).toFixed(2)}%`}
          detail={`Realized ${money(perf.data?.realized_pnl)} · Unrealized ${money(perf.data?.unrealized_pnl)}`}
          icon={perf.data?.total_return && perf.data.total_return >= 0 ? ArrowUpRight : ArrowDownRight}
          tone="green"
        />
      </section>
      <section className="dashboard-grid">
        <article className="panel chart-panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">PERFORMANCE</div>
              <h2>Recorded portfolio value</h2>
            </div>
            <span className="pill pill-muted">Persisted account snapshots</span>
          </div>
          {history.isError ? (
            <ErrorState message={errorText(history.error)} />
          ) : (
            <>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={(history.data ?? []).map((point) => ({
                      label: new Date(point.recorded_at).toLocaleDateString("en-IN", {
                        day: "2-digit",
                        month: "short",
                      }),
                      value: point.equity,
                    }))}
                    margin={{ top: 15, right: 14, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#55d6be" stopOpacity={0.24} />
                        <stop offset="100%" stopColor="#55d6be" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#ffffff0d" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#718096", fontSize: 11 }}
                    />
                    <YAxis
                      domain={["auto", "auto"]}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#718096", fontSize: 11 }}
                      tickFormatter={(v: number) => `₹${Math.round(v / 1000)}k`}
                      width={48}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#111a29",
                        border: "1px solid #263246",
                        borderRadius: 8,
                        color: "#e8edf5",
                      }}
                      formatter={(v) => money(Number(v))}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="#55d6be"
                      strokeWidth={2.5}
                      fill="url(#equityFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <p className="chart-note">
                {(history.data?.length ?? 0) < 2
                  ? "A performance curve will form after multiple account snapshots are recorded."
                  : `${history.data?.length} persisted snapshots · chart shows account history, not interpolated figures.`}
              </p>
            </>
          )}
        </article>
        <article className="panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">MARKET WATCH</div>
              <h2>Available instruments</h2>
            </div>
            <NavLink className="text-link" to="/markets">
              View all <ArrowUpRight size={13} />
            </NavLink>
          </div>
          <QuoteTable
            quotes={quoteRows.slice(0, 4)}
            loading={market.isLoading}
            error={market.isError ? errorText(market.error) : undefined}
          />
        </article>
        <article className="panel news-panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">NEWS INTELLIGENCE</div>
              <h2>Latest signals</h2>
            </div>
            <NavLink className="text-link" to="/news">
              News terminal <ArrowUpRight size={13} />
            </NavLink>
          </div>
          <SignalList
            signals={signals.data?.slice(0, 3) ?? []}
            loading={signals.isLoading}
            error={signals.isError ? errorText(signals.error) : undefined}
          />
        </article>
        <article className="panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">PAPER ACTIVITY</div>
              <h2>Recent orders</h2>
            </div>
            <NavLink className="text-link" to="/paper">
              Order history <ArrowUpRight size={13} />
            </NavLink>
          </div>
          <TradeTable trades={portfolio.data?.recent_trades ?? []} />
        </article>
      </section>
    </>
  );
}
