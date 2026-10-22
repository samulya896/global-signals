import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Search, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import type {
  MarketInstrument,
  MarketQuote,
  MarketType,
  Portfolio,
  Trade,
} from "../lib/api";
import {
  errorText,
  marketQuotePath,
  marketSearchPath,
  money,
  quoteAmount,
} from "../lib/formatters";
import { ErrorState } from "../components/common/ErrorState";
import { MarketStatusBadge } from "../components/common/MarketStatusBadge";
import { PageTitle } from "../components/common/PageTitle";
import { HoldingsTable } from "../components/tables/HoldingsTable";
import { TradeTable } from "../components/tables/TradeTable";

export function PaperPage() {
  const portfolio = useQuery({
    queryKey: ["portfolio"],
    queryFn: () => api<Portfolio>("/api/v1/portfolio"),
  });
  const client = useQueryClient();
  const [marketType, setMarketType] = useState<MarketType>("EQUITY");
  const [search, setSearch] = useState("NIFTYBEES");
  const [submittedSearch, setSubmittedSearch] = useState("NIFTYBEES");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [message, setMessage] = useState("");

  const instruments = useQuery({
    queryKey: ["paper-instruments", marketType, submittedSearch],
    queryFn: () => api<MarketInstrument[]>(marketSearchPath(marketType, submittedSearch)),
    enabled: Boolean(submittedSearch),
  });

  useEffect(() => {
    const rows = instruments.data ?? [];
    if (!rows.some((row) => row.symbol === selectedSymbol)) setSelectedSymbol(rows[0]?.symbol ?? "");
  }, [instruments.data, selectedSymbol]);

  const quote = useQuery({
    queryKey: ["paper-quote", marketType, selectedSymbol],
    queryFn: () => api<MarketQuote>(marketQuotePath(marketType, selectedSymbol)),
    enabled: Boolean(selectedSymbol),
    retry: false,
  });

  const canPaperTrade = quote.data?.status === "LIVE" || quote.data?.metadata.synthetic === true;

  const trade = useMutation({
    mutationFn: (order: {
      market_type: MarketType;
      symbol: string;
      side: "buy" | "sell";
      quantity: number;
    }) =>
      api<Trade>("/api/v1/trades", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(order),
      }),
    onSuccess: (result) => {
      setMessage(
        `${result.side.toUpperCase()} ${result.quantity} ${result.quantity_unit ?? "shares"} of ${result.symbol} simulated at ${result.price}.`
      );
      void client.invalidateQueries({ queryKey: ["portfolio"] });
      void client.invalidateQueries({ queryKey: ["performance"] });
      void client.invalidateQueries({ queryKey: ["portfolio-history"] });
    },
    onError: (error: Error) => setMessage(error.message),
  });

  function changeMarket(value: MarketType) {
    const initialSearch = value === "EQUITY" ? "NIFTYBEES" : "EUR/USD";
    setMarketType(value);
    setSearch(initialSearch);
    setSubmittedSearch(initialSearch);
    setSelectedSymbol("");
    setMessage("");
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const quantity = Number(form.get("quantity"));
    const side = String(form.get("side")) as "buy" | "sell";
    if (!Number.isSafeInteger(quantity) || quantity < 1) {
      setMessage("Enter a positive whole number of shares or base-currency units.");
      return;
    }
    if (!selectedSymbol || !canPaperTrade) {
      setMessage("A current, provider-listed quote is required before a simulated order.");
      return;
    }
    const quoteText = quote.data?.metadata.synthetic
      ? "local synthetic demo price"
      : "fresh provider quote";
    if (
      !window.confirm(
        `Place a virtual ${side.toUpperCase()} for ${quantity} ${selectedSymbol} using the ${quoteText}? Funds are virtual INR and no broker will be contacted.`
      )
    )
      return;
    setMessage("");
    trade.mutate({ market_type: marketType, symbol: selectedSymbol, side, quantity });
  }

  const p = portfolio.data;

  return (
    <>
      <PageTitle
        eyebrow="VIRTUAL EXECUTION"
        title="Paper trading"
        subtitle="The simulator uses one virtual INR account for NSE/BSE equities and selected FX pairs. No broker connection exists."
      />
      <div className="simulation-banner">
        <ShieldCheck size={17} />
        <div>
          <b>Virtual money only</b>
          <span>
            Starting virtual cash: {money(p?.starting_cash ?? 100000)}. Positions, orders, and
            watchlists are isolated to this signed-in user.
          </span>
        </div>
        <span className="banner-badge">NO LIVE TRADING</span>
      </div>
      <section className="trade-layout">
        <article className="panel">
          <div className="eyebrow">NEW SIMULATED ORDER</div>
          <h2>Place virtual order</h2>
          <div className="segmented market-toggle" role="group" aria-label="Order market type">
            <button
              className={marketType === "EQUITY" ? "selected" : ""}
              onClick={() => changeMarket("EQUITY")}
            >
              NSE / BSE equity
            </button>
            <button
              className={marketType === "FOREX" ? "selected" : ""}
              onClick={() => changeMarket("FOREX")}
            >
              Forex
            </button>
          </div>
          <form className="order-form" onSubmit={submit}>
            <label>
              Find instrument
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    setSelectedSymbol("");
                    setSubmittedSearch(search.trim());
                  }
                }}
                placeholder={marketType === "EQUITY" ? "Symbol or company name" : "EUR/USD"}
                maxLength={50}
              />
            </label>
            <button
              className="btn btn-secondary instrument-search-button"
              type="button"
              onClick={() => {
                setSelectedSymbol("");
                setSubmittedSearch(search.trim());
              }}
              disabled={!search.trim() || instruments.isFetching}
            >
              <Search size={15} />
              {instruments.isFetching ? "Searching…" : "Search"}
            </button>
            <label className="instrument-select-label">
              Provider-listed instrument
              <select
                value={selectedSymbol}
                onChange={(event) => setSelectedSymbol(event.target.value)}
                disabled={!instruments.data?.length}
              >
                {(instruments.data ?? []).map((instrument) => (
                  <option key={instrument.symbol} value={instrument.symbol}>
                    {instrument.symbol} · {instrument.name}
                  </option>
                ))}
              </select>
            </label>
            {instruments.isError && (
              <div className="form-error">
                <ErrorState message={errorText(instruments.error)} />
              </div>
            )}
            <div className="quote-preview">
              <b>
                {quote.data
                  ? quoteAmount(quote.data.price, quote.data.quote_currency)
                  : "Quote not available"}
              </b>
              {quote.data && (
                <>
                  <MarketStatusBadge
                    status={quote.data.status}
                    synthetic={quote.data.metadata.synthetic === true}
                  />
                  <small>
                    {quote.data.provider} · {quote.data.price_basis} ·{" "}
                    {new Date(quote.data.source_timestamp).toLocaleString()}
                  </small>
                </>
              )}
              {quote.isError && <small>{errorText(quote.error)}</small>}
            </div>
            <label>
              Action
              <select name="side">
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </label>
            <label>
              {marketType === "FOREX" ? "Base-currency units" : "Shares"}
              <input
                name="quantity"
                type="number"
                min="1"
                max="10000000"
                step="1"
                defaultValue="1"
                required
              />
            </label>
            <button
              className="btn btn-primary"
              disabled={trade.isPending || !canPaperTrade}
            >
              <Play size={15} />
              {trade.isPending ? "Submitting…" : "Confirm simulated order"}
            </button>
          </form>
          {message && (
            <div className={`inline-message ${trade.isError ? "error" : ""}`} role="status">
              {message}
            </div>
          )}
          <p className="fine-print">
            Order value, fees, slippage, FX conversion, cash, and exposure are recorded in virtual
            INR. Synthetic demo quotes are visibly labeled and work only in local development. FX
            prices are composite midpoints and do not include a provider bid/ask spread.
          </p>
        </article>
        <article className="panel">
          <div className="eyebrow">ACCOUNT SUMMARY · INR</div>
          <h2>Virtual portfolio</h2>
          <div className="account-summary">
            <span>Available cash</span>
            <b>{money(p?.cash)}</b>
            <span>Invested value</span>
            <b>{money(p?.market_value)}</b>
            <span>Virtual equity</span>
            <b>{money(p?.equity)}</b>
          </div>
        </article>
      </section>
      <section className="panel section-gap">
        <div className="panel-header">
          <div>
            <div className="eyebrow">POSITIONS</div>
            <h2>Open holdings</h2>
          </div>
        </div>
        <HoldingsTable holdings={p?.holdings ?? []} />
      </section>
      <section className="panel section-gap">
        <div className="panel-header">
          <div>
            <div className="eyebrow">AUDIT TRAIL</div>
            <h2>Order history</h2>
          </div>
        </div>
        <TradeTable trades={p?.recent_trades ?? []} />
      </section>
    </>
  );
}
