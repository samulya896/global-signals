// Backtest page extracted from original monolithic App.tsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, formatMoney } from "../../lib/api";
import { PageTitle } from "../../components/ui/PageTitle";
import { Metric } from "../../components/ui/Metric";
import { BookOpenText, FileUp, Play } from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
// Helper to format money using the same logic as App.tsx
const money = (value) => formatMoney(value ?? 0);
export default function BacktestPage() {
  const [dataset, setDataset] = useState(null);
  const [fileName, setFileName] = useState("");
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [feedback, setFeedback] = useState("");
  const replay = useMutation({
    mutationFn: () => {
      if (!dataset) throw new Error("Choose a historical JSON dataset first.");
      return api("/api/v1/backtest/replay", {
        method: "POST",
        body: JSON.stringify({ ...dataset, data_rights_confirmed: true }),
      });
    },
    onError: (error) => setFeedback(error.message),
    onSuccess: () => setFeedback(""),
  });
  async function selectDataset(event) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    replay.reset();
    setDataset(null);
    setRightsConfirmed(false);
    setFileName(file.name);
    setFeedback("");
    if (file.size > 5_000_000) {
      setFeedback("Choose a JSON file that is 5 MB or smaller.");
      return;
    }
    try {
      const value = JSON.parse(await file.text());
      if (!Array.isArray(value.candles) || !Array.isArray(value.news))
        throw new Error("The JSON must contain candles and news arrays.");
      if (
        typeof value.starting_cash !== "number" ||
        !Number.isFinite(value.starting_cash) ||
        value.starting_cash <= 0
      )
        throw new Error(
          "The JSON must include a positive starting_cash amount in INR.",
        );
      setDataset({
        dataset_name:
          typeof value.dataset_name === "string" && value.dataset_name.trim()
            ? value.dataset_name
            : file.name.replace(/\.json$/i, ""),
        ...(typeof value.strategy_version === "number"
          ? { strategy_version: value.strategy_version }
          : {}),
        starting_cash: value.starting_cash,
        candles: value.candles,
        news: value.news,
      });
    } catch (error) {
      setFeedback(
        error instanceof Error
          ? error.message
          : "The selected file is not valid JSON.",
      );
    }
  }
  const result = replay.data;
  const datasetCandlesByTime = [...(dataset?.candles ?? [])].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
  return (
    <>
      <PageTitle
        eyebrow="STRATEGY RESEARCH"
        title="Historical backtesting"
        subtitle="Replay archived news and market candles in chronological order using virtual INR accounting."
      />
      <div className="simulation-banner warning">
        <BookOpenText size={17} />
        <div>
          <b>Only your supplied history is </b>
          <span>
            Results are not independently verified. No synthetic history, live
            headlines, market provider, broker, or stored portfolio is used by
            this replay.
          </span>
        </div>
        <span className="banner-badge">PAPER ONLY</span>
      </div>

      {/* Input section */}
      <section className="panel backtest-upload section-gap">
        <div className="panel-header">
          <div>
            <div className="eyebrow">HISTORICAL INPUT</div>
            <h2>Load a rights-cleared dataset</h2>
          </div>
          <span className="pill pill-muted">
            Format: docs/BACKTEST_DATA_FORMAT.md
          </span>
        </div>
        <p className="muted-copy">
          Upload JSON with timestamped OHLC candles and archived news
          publication times. The replay accepts up to 20,000 candles and 2,000
          news events, with a 5 MB file limit.
        </p>
        <label className="file-picker">
          <FileUp size={18} />
          <span>{fileName || "Choose historical dataset (.json)"}</span>
          <input
            type="file"
            accept="application/json,.json"
            onChange={(e) => void selectDataset(e)}
            aria-label="Choose historical JSON dataset"
          />
        </label>
        {dataset && (
          <div className="dataset-summary">
            <span>
              <b>{dataset.dataset_name}</b>
            </span>
            <span>{dataset.candles.length.toLocaleString()} candles</span>
            <span>{dataset.news.length.toLocaleString()} news events</span>
            {datasetCandlesByTime.length > 0 && (
              <span>
                Period{" "}
                {new Date(datasetCandlesByTime[0].timestamp).toLocaleDateString(
                  "en-IN",
                )}{" "}
                –{" "}
                {new Date(
                  datasetCandlesByTime[
                    datasetCandlesByTime.length - 1
                  ].timestamp,
                ).toLocaleDateString("en-IN")}
              </span>
            )}
            <span>Starting cash {money(dataset.starting_cash)}</span>
          </div>
        )}
        <label className="rights-confirm">
          <input
            type="checkbox"
            checked={rightsConfirmed}
            onChange={(e) => setRightsConfirmed(e.target.checked)}
          />
          <span>
            I have the right to use and replay this data, and understand the
            result reflects only the dataset I provided.
          </span>
        </label>
        <div className="backtest-actions">
          <button
            className="btn btn-primary"
            disabled={!dataset || !rightsConfirmed || replay.isPending}
            onClick={() => replay.mutate()}
          >
            <Play size={15} />
            {replay.isPending ? "Replaying history…" : "Run virtual replay"}
          </button>
          <span>
            Virtual replay only · nothing is saved to your paper portfolio.
          </span>
        </div>
        {feedback && (
          <div className="inline-message error" role="alert">
            {feedback}
          </div>
        )}
      </section>

      {result && (
        <>
          <section className="metrics-grid backtest-metrics">
            <Metric
              label="ENDING EQUITY"
              value={money(result.ending_equity_inr)}
              detail={`Starting at ${money(result.starting_cash_inr)}`}
            />
            <Metric
              label="TOTAL RETURN"
              value={`${result.return_percent.toFixed(2)}%`}
              detail={`Realized ${money(result.realized_pnl_inr)}`}
            />
            <Metric
              label="MAX DRAWDOWN"
              value={`${result.max_drawdown_percent.toFixed(2)}%`}
              detail="Measured at every replay timestamp"
            />
            <Metric
              label="VIRTUAL FILLS"
              value={result.filled_trade_count.toLocaleString()}
              detail={`${result.rejected_signal_count} rejected · ${result.unfilled_signal_count} unfilled`}
            />
          </section>

          {/* Replay result panels */}
          <section className="panel section-gap backtest-result">
            <div className="panel-header">
              <div>
                <div className="eyebrow">REPLAYED EQUITY</div>
                <h2>{result.dataset_name}</h2>
              </div>
              <span className="pill pill-muted">
                {new Date(result.start_timestamp).toLocaleDateString("en-IN")} –{" "}
                {new Date(result.end_timestamp).toLocaleDateString("en-IN")} ·
                Strategy version {result.strategy_version} ·{" "}
                {result.bar_count.toLocaleString()} bars
              </span>
            </div>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={result.equity_curve.map((point) => ({
                    label: new Date(point.timestamp).toLocaleDateString(
                      "en-IN",
                      {
                        day: "2-digit",
                        month: "short",
                        year: "2-digit",
                      },
                    ),
                    equity: point.equity,
                  }))}
                  margin={{ top: 12, right: 14, left: 0, bottom: 0 }}
                >
                  <CartesianGrid stroke="#d8ddd6" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: "#66716b", fontSize: 10 }}
                  />
                  <YAxis
                    domain={["auto", "auto"]}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: "#66716b", fontSize: 10 }}
                    tickFormatter={(value) => `₹${Math.round(value / 1000)}k`}
                    width={48}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#202724",
                      border: "1px solid #3b4741",
                      borderRadius: 4,
                      color: "#e3eae5",
                    }}
                    formatter={(value) => money(Number(value))}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="#167663"
                    strokeWidth={2}
                    fill="none"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <p className="chart-note">
              Virtual costs: {money(result.fees_inr)} fees and{" "}
              {money(result.slippage_inr)} slippage. {result.notice}
            </p>
          </section>

          {/* Trades table */}
          <section className="panel section-gap">
            <div className="panel-header">
              <div>
                <div className="eyebrow">SIMULATED EXECUTIONS</div>
                <h2>Next-candle fills</h2>
              </div>
            </div>
            {result.trades.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Instrument</th>
                      <th>Side</th>
                      <th>Units</th>
                      <th>Fill</th>
                      <th>Value (INR)</th>
                      <th>Fees</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.slice(0, 30).map((trade, index) => (
                      <tr key={`${trade.timestamp}-${trade.symbol}-${index}`}>
                        <td>
                          {new Date(trade.timestamp).toLocaleString("en-IN")}
                        </td>
                        <td>
                          <b>{trade.symbol}</b>
                          <small>{trade.market_type}</small>
                        </td>
                        <td>
                          <span className={`side-tag ${trade.side}`}>
                            {" "}
                            {trade.side.toUpperCase()}{" "}
                          </span>
                        </td>
                        <td>
                          {trade.quantity.toLocaleString()}{" "}
                          {trade.quantity_unit}
                        </td>
                        <td>{trade.fill_price}</td>
                        <td>{money(trade.value_inr)}</td>
                        <td>{money(trade.fees_inr)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {result.filled_trade_count > 30 && (
                  <p className="chart-note">
                    Showing the first 30 of{" "}
                    {result.filled_trade_count.toLocaleString()} fills; response
                    includes at most 1,000 fill rows.
                  </p>
                )}
              </div>
            ) : (
              <div className="table-empty">
                No signal produced a valid virtual fill for this dataset.
              </div>
            )}
          </section>

          {/* Decisions panel */}
          <section className="panel section-gap">
            <div className="panel-header">
              <div>
                <div className="eyebrow">DECISION AUDIT</div>
                <h2>News decisions and risk checks</h2>
              </div>
              <span className="pill pill-muted">
                {result.signal_count.toLocaleString()} decisions
              </span>
            </div>
            {result.decisions.length ? (
              <div className="decision-list">
                {result.decisions.slice(0, 20).map((decision, index) => (
                  <article
                    className="decision-row"
                    key={`${decision.published_at}-${decision.symbol ?? "event"}-${index}`}
                  >
                    <div>
                      <b>{decision.symbol ?? decision.title}</b>
                      <small>
                        {new Date(decision.published_at).toLocaleString(
                          "en-IN",
                        )}{" "}
                        · {decision.action}
                      </small>
                    </div>
                    <span className={`decision-status ${decision.status}`}>
                      {decision.status}
                    </span>
                    <p>{decision.reason}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="table-empty">
                No archived news was available during this candle range.
              </div>
            )}
            {result.signal_count > 20 && (
              <p className="chart-note">
                Showing the first 20 decisions. The response contains at most
                2,000 decision rows.
              </p>
            )}
          </section>
        </>
      )}
    </>
  );
}
