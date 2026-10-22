import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, RefreshCw, Search, ShieldCheck, Trash2 } from "lucide-react";
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
import type {
  MarketCandle,
  MarketDataStatus,
  MarketInstrument,
  MarketQuote,
  MarketType,
  WatchlistItem,
} from "../lib/api";
import {
  errorText,
  marketQuotePath,
  marketSearchPath,
  quoteAmount,
} from "../lib/formatters";
import { ErrorState } from "../components/common/ErrorState";
import { MarketStatusBadge } from "../components/common/MarketStatusBadge";
import { PageTitle } from "../components/common/PageTitle";
import { TableEmpty } from "../components/common/TableEmpty";

export function MarketsPage() {
  const [marketType, setMarketType] = useState<MarketType>("EQUITY");
  const [search, setSearch] = useState("NIFTYBEES");
  const [submittedSearch, setSubmittedSearch] = useState("NIFTYBEES");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [interval, setInterval] = useState("1day");
  const [feedback, setFeedback] = useState("");
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["market-data-status"],
    queryFn: () => api<MarketDataStatus>("/api/v1/markets/status"),
  });
  const instruments = useQuery({
    queryKey: ["market-instruments", marketType, submittedSearch],
    queryFn: () => api<MarketInstrument[]>(marketSearchPath(marketType, submittedSearch)),
    enabled: Boolean(submittedSearch),
  });
  useEffect(() => {
    const rows = instruments.data ?? [];
    if (!rows.some((row) => row.symbol === selectedSymbol)) setSelectedSymbol(rows[0]?.symbol ?? "");
  }, [instruments.data, selectedSymbol]);
  const quote = useQuery({
    queryKey: ["market-quote", marketType, selectedSymbol],
    queryFn: () => api<MarketQuote>(marketQuotePath(marketType, selectedSymbol)),
    enabled: Boolean(selectedSymbol),
    refetchInterval: 30_000,
    retry: false,
  });
  const candles = useQuery({
    queryKey: ["market-candles", marketType, selectedSymbol, interval],
    queryFn: () => {
      const params = new URLSearchParams({
        market_type: marketType,
        symbol: selectedSymbol,
        interval,
        days: "30",
        limit: "300",
      });
      return api<MarketCandle[]>(`/api/v1/markets/candles?${params.toString()}`);
    },
    enabled: Boolean(selectedSymbol),
    staleTime: 60_000,
    retry: false,
  });
  const watchlist = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api<WatchlistItem[]>("/api/v1/watchlist"),
  });
  const saveWatchlist = useMutation({
    mutationFn: () =>
      api("/api/v1/watchlist", {
        method: "POST",
        body: JSON.stringify({ market_type: marketType, symbol: selectedSymbol }),
      }),
    onSuccess: () => {
      setFeedback(`${selectedSymbol} saved to your watchlist.`);
      void client.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const removeWatchlist = useMutation({
    mutationFn: (item: WatchlistItem) => {
      const params = new URLSearchParams({ market_type: item.market_type, symbol: item.symbol });
      return api(`/api/v1/watchlist?${params.toString()}`, { method: "DELETE" });
    },
    onSuccess: () => {
      setFeedback("Watchlist item removed.");
      void client.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const provider = status.data?.[marketType];
  const synthetic = quote.data?.metadata.synthetic === true;

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = search.trim();
    if (!value) return;
    setSelectedSymbol("");
    setSubmittedSearch(value);
    setFeedback("");
  }
  function changeMarket(value: MarketType) {
    const initialSearch = value === "EQUITY" ? "NIFTYBEES" : "EUR/USD";
    setMarketType(value);
    setSearch(initialSearch);
    setSubmittedSearch(initialSearch);
    setSelectedSymbol("");
    setFeedback("");
  }

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
            Market data is read-only. Orders on the Paper Trading page use virtual INR and never reach a broker.
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
          <MarketStatusBadge status={provider?.configured ? "CONFIGURED" : "UNAVAILABLE"} />
        </div>
        {provider && !provider.configured && (
          <div className="provider-note">
            <b>{provider.provider} is not enabled</b>
            <span>
              {provider.message} Provider keys and authorization status are never displayed.
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
              placeholder={marketType === "EQUITY" ? "e.g. RELIANCE" : "e.g. EUR/USD"}
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
        {instruments.isError && <ErrorState message={errorText(instruments.error)} />}
        <div className="market-detail-grid">
          <div className="market-quote-card">
            <label htmlFor="instrument-select">Provider-listed instrument</label>
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
            {quote.isLoading && <TableEmpty>Loading provider quote…</TableEmpty>}
            {quote.isError && <ErrorState message={errorText(quote.error)} />}
            {quote.data && (
              <>
                <div className="quote-price">
                  {quoteAmount(quote.data.price, quote.data.quote_currency)}{" "}
                  <MarketStatusBadge status={quote.data.status} synthetic={synthetic} />
                </div>
                <div className="quote-meta">
                  <span>
                    {quote.data.provider} · {quote.data.price_basis}
                  </span>
                  <span>Source time {new Date(quote.data.source_timestamp).toLocaleString()}</span>
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
            {candles.isLoading && <TableEmpty>Loading historical candles…</TableEmpty>}
            {candles.isError && <ErrorState message={errorText(candles.error)} />}
            {candles.data?.length ? (
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={candles.data.map((row) => ({
                      label: new Date(row.timestamp).toLocaleDateString("en-IN", {
                        day: "2-digit",
                        month: "short",
                      }),
                      close: row.close,
                    }))}
                    margin={{ top: 10, right: 12, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="marketFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#55d6be" stopOpacity={0.2} />
                        <stop offset="100%" stopColor="#55d6be" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#ffffff0d" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#718096", fontSize: 10 }}
                    />
                    <YAxis
                      domain={["auto", "auto"]}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#718096", fontSize: 10 }}
                      width={55}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#111a29",
                        border: "1px solid #263246",
                        borderRadius: 8,
                        color: "#e8edf5",
                      }}
                      formatter={(value) =>
                        quoteAmount(Number(value), quote.data?.quote_currency ?? "")
                      }
                    />
                    <Area
                      type="monotone"
                      dataKey="close"
                      stroke="#55d6be"
                      strokeWidth={2}
                      fill="url(#marketFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              !candles.isLoading &&
              !candles.isError && <TableEmpty>No historical candles were returned.</TableEmpty>
            )}
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
        {watchlist.isError && <ErrorState message={errorText(watchlist.error)} />}
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
              <div className="table-row" key={`${item.market_type}-${item.symbol}`}>
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
