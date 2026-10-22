import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ResponsiveContainer } from "recharts";
import {
  BookmarkPlus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { api } from "../../lib/api";
import { errorText, quoteAmount } from "../../lib/formatters";
import { ErrorState } from "../../components/feedback/ErrorState";
import { MarketStatusBadge } from "../../components/ui/MarketStatusBadge";
import { PageTitle } from "../../components/ui/PageTitle";
import { TableEmpty } from "../../components/feedback/TableEmpty";
import { useMarketsData } from "./useMarketsData";
export function MarketsPage() {
  const [marketType, setMarketType] = useState("EQUITY");
  const [search, setSearch] = useState("NIFTYBEES");
  const [submittedSearch, setSubmittedSearch] = useState("NIFTYBEES");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [interval, setInterval] = useState("1day");
  const [feedback, setFeedback] = useState("");
  const client = useQueryClient();
  const { status, instruments, quote, candles, watchlist } = useMarketsData({
    marketType,
    submittedSearch,
    selectedSymbol,
    interval,
  });
  useEffect(() => {
    const rows = instruments.data ?? [];
    if (!rows.some((row) => row.symbol === selectedSymbol))
      setSelectedSymbol(rows[0]?.symbol ?? "");
  }, [instruments.data, selectedSymbol]);
  const saveWatchlist = useMutation({
    mutationFn: () =>
      api("/api/v1/watchlist", {
        method: "POST",
        body: JSON.stringify({
          market_type: marketType,
          symbol: selectedSymbol,
        }),
      }),
    onSuccess: () => {
      setFeedback(`${selectedSymbol} saved to your watchlist.`);
      void client.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (error) => setFeedback(error.message),
  });
  const removeWatchlist = useMutation({
    mutationFn: (item) => {
      const params = new URLSearchParams({
        market_type: item.market_type,
        symbol: item.symbol,
      });
      return api(`/api/v1/watchlist?${params.toString()}`, {
        method: "DELETE",
      });
    },
    onSuccess: () => {
      setFeedback("Watchlist item removed.");
      void client.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (error) => setFeedback(error.message),
  });
  const provider = status.data?.[marketType];
  const synthetic = quote.data?.metadata.synthetic === true;
  function submitSearch(event) {
    event.preventDefault();
    const value = search.trim();
    if (!value) return;
    setSelectedSymbol("");
    setSubmittedSearch(value);
    setFeedback("");
  }
  function changeMarket(value) {
    const initialSearch = value === "EQUITY" ? "NIFTYBEES" : "EUR/USD";
    setMarketType(value);
    setSearch(initialSearch);
    setSubmittedSearch(initialSearch);
    setSelectedSymbol("");
    setFeedback("");
  }
  const candleRows = candles.data ?? [];
  const candleMin = candleRows.length
    ? Math.min(...candleRows.map((c) => c.low))
    : 0;
  const candleMax = candleRows.length
    ? Math.max(...candleRows.map((c) => c.high))
    : 1;
  const candleRange = candleMax - candleMin || 1;
  const chartTop = 16;
  const chartBottom = 222;
  const candleY = (price) =>
    chartBottom -
    ((price - candleMin) / candleRange) * (chartBottom - chartTop);
  const candleStep = candleRows.length ? 860 / candleRows.length : 0;
  return (
    <>
      <PageTitle
        eyebrow="NORMALIZED MARKET DATA"
        title="Market watch"
        subtitle="Search supported NSE/BSE instruments or FX pairs, inspect attributed prices, and keep a private watchlist."
        action={
          <button
            className="btn btn-secondary"
            onClick={() => {
              void quote.refetch();
              void candles.refetch();
            }}
          >
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <div className="simulation-banner warning">
        <ShieldCheck size={17} />
        <div>
          <b>Paper trading only</b>
          <span>
            Market data is read-only. Orders on the Paper Trading page use
            virtual INR and never reach a broker.
          </span>
        </div>
        <span className="banner-badge">NO REAL ORDERS</span>
      </div>
      <section className="panel market-workspace">
        <div className="toolbar">
          <div className="segmented" role="group" aria-label="Market type">
            <button
              className={marketType === "EQUITY" ? "selected" : ""}
              onClick={() => changeMarket("EQUITY")}
            >
              NSE / BSE equities
            </button>
            <button
              className={marketType === "FOREX" ? "selected" : ""}
              onClick={() => changeMarket("FOREX")}
            >
              Forex pairs
            </button>
          </div>
          <MarketStatusBadge
            status={provider?.configured ? "CONFIGURED" : "UNAVAILABLE"}
          />
        </div>
        {provider && !provider.configured && (
          <div className="provider-note">
            <b>{provider.provider} is not enabled</b>
            <span>
              {provider.message} Provider keys and authorization status are
              never displayed.
            </span>
          </div>
        )}
        <form className="market-search" onSubmit={submitSearch}>
          <label htmlFor="instrument-search">
            Search{" "}
            {marketType === "EQUITY"
              ? "NSE/BSE symbol or company"
              : "currency pair (for example EUR/USD)"}
          </label>
          <div>
            <input
              id="instrument-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              maxLength={50}
              placeholder={
                marketType === "EQUITY" ? "e.g. RELIANCE" : "e.g. EUR/USD"
              }
            />
            <button
              className="btn btn-secondary"
              type="submit"
              disabled={instruments.isFetching}
            >
              <Search size={15} />
              {instruments.isFetching ? "Searching…" : "Search"}
            </button>
          </div>
        </form>
        {instruments.isError && (
          <ErrorState message={errorText(instruments.error)} />
        )}
        <div className="market-detail-grid">
          <div className="market-quote-card">
            <label htmlFor="instrument-select">
              Provider-listed instrument
            </label>
            <select
              id="instrument-select"
              value={selectedSymbol}
              onChange={(event) => setSelectedSymbol(event.target.value)}
              disabled={!instruments.data?.length}
            >
              {(instruments.data ?? []).map((item) => (
                <option key={item.symbol} value={item.symbol}>
                  {item.symbol} · {item.name}
                </option>
              ))}
            </select>
            {quote.isLoading && (
              <TableEmpty>Loading provider quote…</TableEmpty>
            )}
            {quote.isError && <ErrorState message={errorText(quote.error)} />}
            {quote.data && (
              <>
                <div className="quote-price">
                  {quoteAmount(quote.data.price, quote.data.quote_currency)}{" "}
                  <MarketStatusBadge
                    status={quote.data.status}
                    synthetic={synthetic}
                  />
                </div>
                <div className="quote-meta">
                  <span>
                    {quote.data.provider} · {quote.data.price_basis}
                  </span>
                  <span>
                    Source time{" "}
                    {new Date(quote.data.source_timestamp).toLocaleString()}
                  </span>
                </div>
                <div className="quote-meta">
                  <span>
                    Bid{" "}
                    {quote.data.bid == null
                      ? "not supplied"
                      : quoteAmount(quote.data.bid, quote.data.quote_currency)}
                  </span>
                  <span>
                    Ask{" "}
                    {quote.data.ask == null
                      ? "not supplied"
                      : quoteAmount(quote.data.ask, quote.data.quote_currency)}
                  </span>
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => saveWatchlist.mutate()}
                  disabled={!selectedSymbol || saveWatchlist.isPending}
                >
                  <BookmarkPlus size={15} />
                  {saveWatchlist.isPending ? "Saving…" : "Add to my watchlist"}
                </button>
              </>
            )}
          </div>
          <div className="panel market-chart-card">
            <div className="panel-header">
              <div>
                <div className="eyebrow">HISTORICAL PRICE</div>
                <h2>Provider candles</h2>
              </div>
              <select
                aria-label="Chart interval"
                value={interval}
                onChange={(event) => setInterval(event.target.value)}
              >
                <option value="1day">Daily</option>
                <option value="1h">Hourly</option>
                <option value="15min">15 minutes</option>
                <option value="5min">5 minutes</option>
              </select>
            </div>
            {candles.isLoading && (
              <TableEmpty>Loading historical candles…</TableEmpty>
            )}
            {candles.isError && (
              <ErrorState message={errorText(candles.error)} />
            )}
            {candles.data?.length ? (
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <svg
                    className="candlestick-chart"
                    viewBox="0 0 900 260"
                    preserveAspectRatio="none"
                    role="img"
                    aria-label={`Provider OHLC candlestick chart for ${selectedSymbol}`}
                  >
                    {[0, 1, 2, 3, 4].map((tick) => {
                      const y =
                        chartTop + ((chartBottom - chartTop) * tick) / 4;
                      const price = candleMax - (candleRange * tick) / 4;
                      return (
                        <g key={tick}>
                          <line
                            x1="42"
                            x2="896"
                            y1={y}
                            y2={y}
                            className="chart-gridline"
                          />
                          <text
                            x="38"
                            y={y + 4}
                            textAnchor="end"
                            className="chart-axis-label"
                          >
                            {price.toLocaleString(undefined, {
                              maximumFractionDigits: 2,
                            })}
                          </text>
                        </g>
                      );
                    })}
                    {candleRows.map((row, index) => {
                      const center = 44 + index * candleStep + candleStep / 2;
                      const up = row.close >= row.open;
                      const bodyTop = candleY(Math.max(row.open, row.close));
                      const bodyBottom = candleY(Math.min(row.open, row.close));
                      const date = new Date(row.timestamp);
                      const timestamp =
                        interval === "1day"
                          ? date.toLocaleDateString()
                          : date.toLocaleString();
                      return (
                        <g
                          key={`${row.timestamp}-${index}`}
                          className={up ? "candle-up" : "candle-down"}
                        >
                          <title>{`${timestamp} · O ${row.open} · H ${row.high} · L ${row.low} · C ${row.close}${row.volume == null ? "" : ` · Vol ${row.volume}`}`}</title>
                          <line
                            x1={center}
                            x2={center}
                            y1={candleY(row.high)}
                            y2={candleY(row.low)}
                            stroke="currentColor"
                            strokeWidth="1"
                            vectorEffect="non-scaling-stroke"
                          />
                          <rect
                            x={Math.max(
                              43,
                              center - Math.max(1, candleStep * 0.29),
                            )}
                            y={bodyTop}
                            width={Math.max(1, Math.min(8, candleStep * 0.58))}
                            height={Math.max(bodyBottom - bodyTop, 1.4)}
                            fill="currentColor"
                            vectorEffect="non-scaling-stroke"
                          />
                        </g>
                      );
                    })}
                    {candleRows
                      .filter(
                        (_, index) =>
                          index === 0 ||
                          index === candleRows.length - 1 ||
                          index === Math.floor(candleRows.length / 2),
                      )
                      .map((row) => (
                        <text
                          key={`date-${row.timestamp}`}
                          x={44 + candleRows.indexOf(row) * candleStep}
                          y="250"
                          className="chart-axis-label"
                        >
                          {new Date(row.timestamp).toLocaleDateString(
                            undefined,
                            { month: "short", day: "numeric" },
                          )}
                        </text>
                      ))}
                  </svg>
                </ResponsiveContainer>
              </div>
            ) : (
              !candles.isLoading &&
              !candles.isError && (
                <TableEmpty>No historical candles were returned.</TableEmpty>
              )
            )}
            {candles.data?.length ? (
              <p className="chart-note">
                {candles.data.length.toLocaleString()} provider OHLC candles ·
                Hover a candle for open, high, low and close.
              </p>
            ) : null}
          </div>
        </div>
        {feedback && (
          <div className="inline-message" role="status">
            {feedback}
          </div>
        )}
      </section>
      <section className="panel section-gap">
        <div className="panel-header">
          <div>
            <div className="eyebrow">PRIVATE TO THIS ACCOUNT</div>
            <h2>My watchlist</h2>
          </div>
        </div>
        {watchlist.isError && (
          <ErrorState message={errorText(watchlist.error)} />
        )}
        {!watchlist.data?.length ? (
          <TableEmpty>
            Save a searched instrument to build your account-scoped watchlist.
          </TableEmpty>
        ) : (
          <div className="data-table">
            <div className="table-row table-head">
              <span>MARKET / INSTRUMENT</span>
              <span>CURRENCY</span>
              <span>ACTION</span>
            </div>
            {watchlist.data.map((item) => (
              <div
                className="table-row"
                key={`${item.market_type}-${item.symbol}`}
              >
                <span className="instrument">
                  <button
                    className="watchlist-symbol"
                    onClick={() => {
                      changeMarket(item.market_type);
                      setSearch(item.symbol);
                      setSubmittedSearch(item.symbol);
                      setSelectedSymbol(item.symbol);
                    }}
                  >
                    {item.symbol}
                  </button>
                  <small>{item.name}</small>
                </span>
                <span className="mono">{item.quote_currency}</span>
                <span>
                  <button
                    className="icon-button"
                    aria-label={`Remove ${item.symbol}`}
                    onClick={() => removeWatchlist.mutate(item)}
                  >
                    <Trash2 size={14} />
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
