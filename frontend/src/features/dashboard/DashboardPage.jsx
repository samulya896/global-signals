import { NavLink } from "react-router-dom";
import { ArrowUpRight, RefreshCw } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { errorText, money } from "../../lib/formatters";
import { ErrorState } from "../../components/feedback/ErrorState";
import { Metric } from "../../components/ui/Metric";
import { PageTitle } from "../../components/ui/PageTitle";
import { QuoteTable } from "../../components/tables/QuoteTable";
import { SignalList } from "../../components/tables/SignalList";
import { TradeTable } from "../../components/tables/TradeTable";
import { TableSkeleton } from "../../components/feedback/TableSkeleton";
import { useDashboardData } from "./useDashboardData";
export function DashboardPage() {
  const {
    portfolio,
    performance: perf,
    market,
    signals,
    history,
  } = useDashboardData();
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
        title="Dashboard"
        subtitle="Portfolio value, market quotes and recent account activity."
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
      {portfolio.isError && (
        <ErrorState message={`Portfolio: ${errorText(portfolio.error)}`} />
      )}
      <section className="metrics-grid">
        <Metric
          label="PORTFOLIO EQUITY"
          value={
            portfolio.data
              ? money(portfolio.data.equity)
              : portfolio.isLoading
                ? "Loading…"
                : "Unavailable"
          }
          detail={
            portfolio.data
              ? "Virtual cash + marked holdings"
              : "Account value not available"
          }
        />
        <Metric
          label="AVAILABLE CASH"
          value={
            portfolio.data
              ? money(portfolio.data.cash)
              : portfolio.isLoading
                ? "Loading…"
                : "Unavailable"
          }
          detail="Paper buying power"
        />
        <Metric
          label="INVESTED VALUE"
          value={
            portfolio.data
              ? money(portfolio.data.market_value)
              : portfolio.isLoading
                ? "Loading…"
                : "Unavailable"
          }
          detail="Current simulated market value"
        />
        <Metric
          label="TOTAL RETURN"
          value={
            perf.data
              ? `${perf.data.total_return.toFixed(2)}%`
              : perf.isLoading
                ? "Loading…"
                : "Unavailable"
          }
          detail={
            perf.data
              ? `Realized ${money(perf.data.realized_pnl)} · Unrealized ${money(perf.data.unrealized_pnl)}`
              : "Performance summary"
          }
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
          ) : history.isLoading ? (
            <div className="chart-loading" role="status" aria-busy="true">
              Loading recorded account history…
            </div>
          ) : (
            <>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={(history.data ?? []).map((point) => ({
                      label: new Date(point.recorded_at).toLocaleDateString(
                        "en-IN",
                        {
                          day: "2-digit",
                          month: "short",
                        },
                      ),
                      value: point.equity,
                    }))}
                    margin={{ top: 15, right: 14, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid stroke="#35413b" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#9ca8a1", fontSize: 11 }}
                    />
                    <YAxis
                      domain={["auto", "auto"]}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#9ca8a1", fontSize: 11 }}
                      tickFormatter={(v) => `₹${Math.round(v / 1000)}k`}
                      width={48}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#202724",
                        border: "1px solid #3b4741",
                        borderRadius: 4,
                        color: "#e3eae5",
                      }}
                      formatter={(v) => money(Number(v))}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="#77bda9"
                      strokeWidth={2}
                      fill="none"
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
          {portfolio.isLoading ? (
            <TableSkeleton rows={3} columns={3} />
          ) : portfolio.isError ? (
            <ErrorState message={errorText(portfolio.error)} />
          ) : (
            <TradeTable trades={portfolio.data?.recent_trades ?? []} />
          )}
        </article>
      </section>
    </>
  );
}
