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
import { PageTitle } from "../../components/ui/PageTitle";
import { QuoteTable } from "../../components/tables/QuoteTable";
import { SignalList } from "../../components/tables/SignalList";
import { TradeTable } from "../../components/tables/TradeTable";
import { TableSkeleton } from "../../components/feedback/TableSkeleton";
import { TableEmpty } from "../../components/feedback/TableEmpty";
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
            .toUpperCase() + " · VIRTUAL ACCOUNT"
        }
        title="Dashboard"
        subtitle="A record of your virtual portfolio, provider data, and recent simulated activity."
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
      <section className="dashboard-hero" aria-label="Portfolio summary">
        <div className="equity-lead">
          <span className="eyebrow">PAPER ACCOUNT · INR</span>
          <strong>
            {portfolio.data
              ? money(portfolio.data.equity)
              : portfolio.isLoading
                ? "Loading…"
                : "Unavailable"}
          </strong>
          <span>Current virtual equity</span>
        </div>
        <dl className="equity-details">
          <div>
            <dt>Available cash</dt>
            <dd>
              {portfolio.data
                ? money(portfolio.data.cash)
                : portfolio.isLoading
                  ? "Loading…"
                  : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt>Marked holdings</dt>
            <dd>
              {portfolio.data
                ? money(portfolio.data.market_value)
                : portfolio.isLoading
                  ? "Loading…"
                  : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt>Total return</dt>
            <dd>
              {perf.data
                ? `${perf.data.total_return.toFixed(2)}%`
                : perf.isLoading
                  ? "Loading…"
                  : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt>Realized / unrealized</dt>
            <dd className="equity-detail-copy">
              {perf.data
                ? `${money(perf.data.realized_pnl)} / ${money(perf.data.unrealized_pnl)}`
                : perf.isLoading
                  ? "Loading…"
                  : "Unavailable"}
            </dd>
          </div>
        </dl>
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
          ) : history.data?.length ? (
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
                    <CartesianGrid stroke="#d8ddd6" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#66716b", fontSize: 11 }}
                    />
                    <YAxis
                      domain={["auto", "auto"]}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#66716b", fontSize: 11 }}
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
                      stroke="#167663"
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
          ) : (
            <TableEmpty>
              No persisted account snapshots are available yet. The chart will
              appear after portfolio activity is recorded.
            </TableEmpty>
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
