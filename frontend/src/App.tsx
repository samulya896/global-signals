import { useEffect, useState } from "react";
import type { ElementType, FormEvent, ReactNode } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3, BookOpenText, BookmarkPlus,
  BriefcaseBusiness, ChevronDown, CircleHelp, Clock3, Gauge,
  LayoutDashboard, Menu, Newspaper, Play, RefreshCw, Settings2,
  FileUp, Search, ShieldCheck, SlidersHorizontal, Trash2, WalletCards, X,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, formatMoney, isSafeArticleUrl, setCsrfToken } from "./lib/api";
import "./market.css";
import type { AuthUser, HistoricalReplay, HistoricalReplayRequest, MarketCandle, MarketDataStatus, MarketInstrument, MarketQuote, MarketType, Performance, Portfolio, PortfolioPoint, Quote, Signal, StrategyConfig, StrategyPreview, StrategyVersion, Trade, WatchlistItem } from "./lib/api";

const nav = [
  { label: "Overview", to: "/", icon: LayoutDashboard },
  { label: "News terminal", to: "/news", icon: Newspaper },
  { label: "Market watch", to: "/markets", icon: Activity },
  { label: "Paper trading", to: "/paper", icon: WalletCards },
  { label: "Strategy lab", to: "/strategy", icon: SlidersHorizontal },
  { label: "Backtesting", to: "/backtest", icon: BarChart3 },
  { label: "Settings", to: "/settings", icon: Settings2 },
];

function usePortfolio() {
  return useQuery({ queryKey: ["portfolio"], queryFn: () => api<Portfolio>("/api/v1/portfolio") });
}
function useMarket() {
  return useQuery({ queryKey: ["market"], queryFn: () => api<Quote[]>("/api/v1/market") });
}
function useSignals() {
  return useQuery({ queryKey: ["signals"], queryFn: () => api<Signal[]>("/api/v1/signals") });
}
function money(value?: number) { return formatMoney(value ?? 0); }
function errorText(error: Error | null) { return error?.message ?? "Service is unavailable"; }
function quoteAmount(value: number, currency: string) {
  return currency === "INR" ? money(value) : `${new Intl.NumberFormat("en-US", { minimumFractionDigits: currency === "JPY" ? 3 : 5, maximumFractionDigits: currency === "JPY" ? 3 : 5 }).format(value)} ${currency}`;
}
function marketSearchPath(marketType: MarketType, query: string) {
  const params = new URLSearchParams({ market_type: marketType, q: query, limit: "20" });
  return `/api/v1/markets/instruments?${params.toString()}`;
}
function marketQuotePath(marketType: MarketType, symbol: string) {
  const params = new URLSearchParams({ market_type: marketType, symbol });
  return `/api/v1/markets/quote?${params.toString()}`;
}

function Shell({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const market = useMarket();
  const spy = market.data?.[0];
  return <div className="app-frame">
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="brand"><div className="brand-symbol">G<span>.</span></div><div><b>GLOBAL SIGNALS</b><small>MARKET INTELLIGENCE</small></div><button className="icon-button close-nav" onClick={() => setOpen(false)} aria-label="Close navigation"><X size={17}/></button></div>
      <div className="workspace"><span className="workspace-icon"><BriefcaseBusiness size={15}/></span><div><b>Paper portfolio</b><small>Personal workspace</small></div><ChevronDown size={14}/></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav>{nav.map(({ label, to, icon: Icon }) => <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon size={17}/><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="connection"><span className="status-dot"/><div><b>SIMULATION MODE</b><small>Orders are virtual only</small></div></div><div className="user-row"><div className="avatar">{user.email.slice(0,2).toUpperCase()}</div><div><b>{user.email}</b><small>Personal paper account</small></div><button className="logout-button" onClick={onLogout}>Sign out</button></div></div>
    </aside>
    {open && <button className="scrim" onClick={() => setOpen(false)} aria-label="Close menu"/>}
    <div className="main-column">
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu size={19}/></button><div className="crumb"><span>Workspace</span><span className="slash">/</span><strong>Market overview</strong></div><div className="top-actions"><div className="market-status"><span className="status-dot"/> {spy?.provider ?? "Market data"} <span className="top-divider">·</span> {spy ? `${spy.symbol} ${quoteAmount(spy.price, spy.quote_currency ?? spy.currency ?? "INR")}` : "Quotes loading"}</div><div className="top-avatar" aria-label="Local demo account">GS</div></div></header>
      <main className="content"><Routes>
        <Route path="/" element={<Dashboard/>}/>
        <Route path="/news" element={<NewsPage/>}/>
        <Route path="/markets" element={<MarketsPage/>}/>
        <Route path="/paper" element={<PaperPage/>}/>
        <Route path="/strategy" element={<StrategyPage/>}/>
        <Route path="/backtest" element={<BacktestPage/>}/>
        <Route path="/settings" element={<SettingsPage/>}/>
      </Routes></main>
      <footer className="footer"><span>GLOBAL SIGNALS · LOCAL SIMULATION ENVIRONMENT</span><span>Educational use only <span className="footer-dot">●</span> No real orders</span></footer>
    </div>
  </div>;
}

function PageTitle({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle: string; action?: ReactNode }) {
  return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>{action}</div>;
}
function Metric({ label, value, detail, icon: Icon, tone = "neutral" }: { label: string; value: string; detail: string; icon: ElementType; tone?: string }) {
  return <div className="metric-card"><div className="metric-head"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={16}/></span></div><strong>{value}</strong><small>{detail}</small></div>;
}
function ErrorState({ message }: { message: string }) { return <div className="error-state"><CircleHelp size={18}/><span>{message}</span></div>; }
function TableEmpty({ children }: { children: React.ReactNode }) { return <div className="table-empty">{children}</div>; }

function Dashboard() {
  const portfolio = usePortfolio(); const perf = useQuery({ queryKey: ["performance"], queryFn: () => api<Performance>("/api/v1/performance") });
  const market = useMarket(); const signals = useSignals();
  const history = useQuery({ queryKey:["portfolio-history"], queryFn:()=>api<PortfolioPoint[]>("/api/v1/portfolio/history") });
  const quoteRows = market.data ?? [];
  return <>
    <PageTitle eyebrow={new Date().toLocaleDateString("en-IN",{weekday:"long",day:"2-digit",month:"long",year:"numeric"}).toUpperCase()+" · PAPER ACCOUNT"} title="Market overview" subtitle="A clear view of your simulated portfolio and the signals behind it." action={<button className="btn btn-secondary" onClick={() => { void portfolio.refetch(); void market.refetch(); void signals.refetch(); void perf.refetch(); }}><RefreshCw size={15}/> Refresh</button>}/>
    <div className="simulation-banner"><ShieldCheck size={17}/><div><b>Simulation environment</b><span>Every order uses virtual funds. No brokerage connection or real trade execution is available.</span></div><span className="banner-badge">PAPER ONLY</span></div>
    {portfolio.isError && <ErrorState message={`Portfolio: ${errorText(portfolio.error)}`}/>}
    <section className="metrics-grid">
      <Metric label="PORTFOLIO EQUITY" value={money(portfolio.data?.equity)} detail="Virtual cash + marked holdings" icon={WalletCards} tone="blue"/>
      <Metric label="AVAILABLE CASH" value={money(portfolio.data?.cash)} detail="Paper buying power" icon={Gauge}/>
      <Metric label="INVESTED VALUE" value={money(portfolio.data?.market_value)} detail="Current simulated market value" icon={BriefcaseBusiness} tone="purple"/>
      <Metric label="TOTAL RETURN" value={`${(perf.data?.total_return ?? 0).toFixed(2)}%`} detail={`Realized ${money(perf.data?.realized_pnl)} · Unrealized ${money(perf.data?.unrealized_pnl)}`} icon={perf.data?.total_return && perf.data.total_return >= 0 ? ArrowUpRight : ArrowDownRight} tone="green"/>
    </section>
    <section className="dashboard-grid">
      <article className="panel chart-panel"><div className="panel-header"><div><div className="eyebrow">PERFORMANCE</div><h2>Recorded portfolio value</h2></div><span className="pill pill-muted">Persisted account snapshots</span></div>{history.isError?<ErrorState message={errorText(history.error)}/>:<><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={(history.data??[]).map(point=>({label:new Date(point.recorded_at).toLocaleDateString("en-IN",{day:"2-digit",month:"short"}),value:point.equity}))} margin={{top:15,right:14,left:0,bottom:0}}><defs><linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#55d6be" stopOpacity={0.24}/><stop offset="100%" stopColor="#55d6be" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#ffffff0d" vertical={false}/><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{fill:"#718096",fontSize:11}}/><YAxis domain={['auto','auto']} tickLine={false} axisLine={false} tick={{fill:"#718096",fontSize:11}} tickFormatter={(v:number)=>`₹${Math.round(v/1000)}k`} width={48}/><Tooltip contentStyle={{background:"#111a29",border:"1px solid #263246",borderRadius:8,color:"#e8edf5"}} formatter={(v)=>money(Number(v))}/><Area type="monotone" dataKey="value" stroke="#55d6be" strokeWidth={2.5} fill="url(#equityFill)"/></AreaChart></ResponsiveContainer></div><p className="chart-note">{(history.data?.length??0)<2?"A performance curve will form after multiple account snapshots are recorded.":`${history.data?.length} persisted snapshots · chart shows account history, not interpolated figures.`}</p></>}</article>
      <article className="panel"><div className="panel-header"><div><div className="eyebrow">MARKET WATCH</div><h2>Available instruments</h2></div><NavLink className="text-link" to="/markets">View all <ArrowUpRight size={13}/></NavLink></div><QuoteTable quotes={quoteRows.slice(0,4)} loading={market.isLoading} error={market.isError ? errorText(market.error) : undefined}/></article>
      <article className="panel news-panel"><div className="panel-header"><div><div className="eyebrow">NEWS INTELLIGENCE</div><h2>Latest signals</h2></div><NavLink className="text-link" to="/news">News terminal <ArrowUpRight size={13}/></NavLink></div><SignalList signals={signals.data?.slice(0,3) ?? []} loading={signals.isLoading} error={signals.isError ? errorText(signals.error) : undefined}/></article>
      <article className="panel"><div className="panel-header"><div><div className="eyebrow">PAPER ACTIVITY</div><h2>Recent orders</h2></div><NavLink className="text-link" to="/paper">Order history <ArrowUpRight size={13}/></NavLink></div><TradeTable trades={portfolio.data?.recent_trades ?? []}/></article>
    </section>
  </>;
}

function QuoteTable({ quotes, loading, error }: { quotes: Quote[]; loading?: boolean; error?: string }) {
  if (loading) return <TableEmpty>Loading simulated quotes…</TableEmpty>;
  if (error) return <ErrorState message={error}/>;
  if (!quotes.length) return <TableEmpty>Quote data is unavailable.</TableEmpty>;
  return <div className="data-table"><div className="table-row table-head"><span>INSTRUMENT</span><span>PRICE</span><span>DAILY CHANGE</span></div>{quotes.map(q=><div className="table-row" key={q.symbol}><span className="instrument"><b>{q.symbol}</b><small>{q.provider ?? q.source}{q.status ? ` · ${q.status}` : ""}</small></span><span className="mono">{quoteAmount(q.price, q.quote_currency ?? q.currency ?? "INR")}</span><span className={`change ${(q.change_percent ?? 0) >= 0 ? "positive" : "negative"}`}>{q.change_percent == null ? "—" : `${q.change_percent >= 0 ? "+" : ""}${q.change_percent.toFixed(2)}%`}</span></div>)}</div>;
}
function SignalList({ signals, loading, error }: { signals: Signal[]; loading?: boolean; error?: string }) {
  if (loading) return <TableEmpty>Analyzing available headlines…</TableEmpty>;
  if (error) return <ErrorState message={error}/>;
  if (!signals.length) return <TableEmpty>No signals available.</TableEmpty>;
  return <div className="signal-list">{signals.map((s,i)=><div className="signal-row" key={`${s.title}-${i}`}><span className={`signal-mark ${s.action.toLowerCase()}`}>{s.action === "BUY" ? <ArrowUpRight size={16}/> : s.action === "SELL" ? <ArrowDownRight size={16}/> : <Activity size={15}/>}</span><div className="signal-copy"><b>{s.title}</b><small>{s.symbols.join(", ")} <span>·</span> {s.category} <span>·</span> {s.matched_keywords.join(", ") || "No matching terms"}</small></div><span className={`signal-pill ${s.action.toLowerCase()}`}>{s.action}</span></div>)}</div>;
}
function TradeTable({ trades }: { trades: Trade[] }) {
  if (!trades.length) return <TableEmpty>No simulated orders yet. Visit Paper trading to place a virtual order.</TableEmpty>;
  return <div className="data-table"><div className="table-row table-head"><span>ORDER</span><span>VALUE · INR</span><span>STATUS</span></div>{trades.slice(0,5).map((t,i)=><div className="table-row" key={`${t.timestamp}-${i}`}><span className="instrument"><b>{t.side.toUpperCase()} {t.symbol}</b><small>{t.quantity} {t.quantity_unit ?? "shares"} · {new Date(t.timestamp).toLocaleString()}</small><small>Fee {money(t.fees)} · slippage {money(t.slippage)}</small></span><span className="mono">{money(t.value_inr ?? t.value)}</span><span className="pill pill-green">SIMULATED</span></div>)}</div>;
}

function NewsPage() {
  const query = useQuery({ queryKey:["news","live"], queryFn:()=>api<Record<string,unknown>[]>("/api/v1/news/live") });
  const status = useQuery({ queryKey:["news-status"], queryFn:()=>api<{configured:boolean;production_authorized:boolean;message:string}>("/api/v1/news/status") });
  const news = query.data ?? [];
  return <><PageTitle eyebrow="NEWS INTELLIGENCE" title="News terminal" subtitle="Provider-attributed articles only. Sample headlines are not shown or mixed into live results." action={<button className="btn btn-secondary" onClick={()=>void query.refetch()}><RefreshCw size={15}/> Refresh provider</button>}/>{status.data&&!status.data.configured&&<div className="simulation-banner warning"><CircleHelp size={17}/><div><b>News provider is not configured</b><span>{status.data.message} No sample articles or invented publication times are displayed.</span></div><span className="banner-badge">NO LIVE FEED</span></div>}{query.isError&&<ErrorState message={errorText(query.error)}/>}<div className="news-grid">{news.map((article,i)=><article className="panel news-card" key={String(article.id??i)}><div className="eyebrow">{String(article.category??"UNCLASSIFIED").toUpperCase()} · {String(article.source??"Provider source unavailable")}</div><h2>{String(article.title??"Untitled headline")}</h2><p>{String(article.description??"No description supplied by the provider.")}</p><div className="news-footer"><span><Clock3 size={13}/>{String(article.published_at??"Publication time unavailable")}</span><span>Retrieved {String(article.retrieved_at??"timestamp unavailable")}</span>{typeof article.url==="string"&&isSafeArticleUrl(article.url)&&<a href={article.url} target="_blank" rel="noopener noreferrer">Open original <ArrowUpRight size={13}/></a>}</div></article>)}</div>{!query.isLoading&&!query.isError&&!news.length&&status.data?.configured&&<div className="panel"><TableEmpty>The provider returned no matching articles.</TableEmpty></div>}</>;
}

function MarketStatusBadge({ status, synthetic }: { status?: string; synthetic?: boolean }) {
  const label = synthetic ? "SYNTHETIC DEMO" : status ?? "UNAVAILABLE";
  return <span className={`pill ${status === "LIVE" || synthetic ? "pill-green" : "pill-muted"}`}>{label}</span>;
}

function MarketsPage() {
  const [marketType, setMarketType] = useState<MarketType>("EQUITY");
  const [search, setSearch] = useState("NIFTYBEES");
  const [submittedSearch, setSubmittedSearch] = useState("NIFTYBEES");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [interval, setInterval] = useState("1day");
  const [feedback, setFeedback] = useState("");
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["market-data-status"], queryFn: () => api<MarketDataStatus>("/api/v1/markets/status") });
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
      const params = new URLSearchParams({ market_type: marketType, symbol: selectedSymbol, interval, days: "30", limit: "300" });
      return api<MarketCandle[]>(`/api/v1/markets/candles?${params.toString()}`);
    },
    enabled: Boolean(selectedSymbol),
    staleTime: 60_000,
    retry: false,
  });
  const watchlist = useQuery({ queryKey: ["watchlist"], queryFn: () => api<WatchlistItem[]>("/api/v1/watchlist") });
  const saveWatchlist = useMutation({
    mutationFn: () => api("/api/v1/watchlist", { method: "POST", body: JSON.stringify({ market_type: marketType, symbol: selectedSymbol }) }),
    onSuccess: () => { setFeedback(`${selectedSymbol} saved to your watchlist.`); void client.invalidateQueries({ queryKey: ["watchlist"] }); },
    onError: (error: Error) => setFeedback(error.message),
  });
  const removeWatchlist = useMutation({
    mutationFn: (item: WatchlistItem) => {
      const params = new URLSearchParams({ market_type: item.market_type, symbol: item.symbol });
      return api(`/api/v1/watchlist?${params.toString()}`, { method: "DELETE" });
    },
    onSuccess: () => { setFeedback("Watchlist item removed."); void client.invalidateQueries({ queryKey: ["watchlist"] }); },
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

  return <>
    <PageTitle eyebrow="NORMALIZED MARKET DATA" title="Market watch" subtitle="Search supported NSE/BSE instruments or FX pairs, inspect attributed prices, and keep a private watchlist." action={<button className="btn btn-secondary" onClick={() => { void quote.refetch(); void candles.refetch(); }}><RefreshCw size={15}/> Refresh</button>}/>
    <div className="simulation-banner warning"><ShieldCheck size={17}/><div><b>Paper trading only</b><span>Market data is read-only. Orders on the Paper Trading page use virtual INR and never reach a broker.</span></div><span className="banner-badge">NO REAL ORDERS</span></div>
    <section className="panel market-workspace">
      <div className="toolbar"><div className="segmented" role="group" aria-label="Market type"><button className={marketType === "EQUITY" ? "selected" : ""} onClick={() => changeMarket("EQUITY")}>NSE / BSE equities</button><button className={marketType === "FOREX" ? "selected" : ""} onClick={() => changeMarket("FOREX")}>Forex pairs</button></div><MarketStatusBadge status={provider?.configured ? "CONFIGURED" : "UNAVAILABLE"}/></div>
      {provider && !provider.configured && <div className="provider-note"><b>{provider.provider} is not enabled</b><span>{provider.message} Provider keys and authorization status are never displayed.</span></div>}
      <form className="market-search" onSubmit={submitSearch}><label htmlFor="instrument-search">Search {marketType === "EQUITY" ? "NSE/BSE symbol or company" : "currency pair (for example EUR/USD)"}</label><div><input id="instrument-search" value={search} onChange={(event) => setSearch(event.target.value)} maxLength={50} placeholder={marketType === "EQUITY" ? "e.g. RELIANCE" : "e.g. EUR/USD"}/><button className="btn btn-secondary" type="submit" disabled={instruments.isFetching}><Search size={15}/>{instruments.isFetching ? "Searching…" : "Search"}</button></div></form>
      {instruments.isError && <ErrorState message={errorText(instruments.error)}/>}
      <div className="market-detail-grid">
        <div className="market-quote-card">
          <label htmlFor="instrument-select">Provider-listed instrument</label>
          <select id="instrument-select" value={selectedSymbol} onChange={(event) => setSelectedSymbol(event.target.value)} disabled={!instruments.data?.length}>
            {(instruments.data ?? []).map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol} · {item.name}</option>)}
          </select>
          {quote.isLoading && <TableEmpty>Loading provider quote…</TableEmpty>}
          {quote.isError && <ErrorState message={errorText(quote.error)}/>}
          {quote.data && <>
            <div className="quote-price">{quoteAmount(quote.data.price, quote.data.quote_currency)} <MarketStatusBadge status={quote.data.status} synthetic={synthetic}/></div>
            <div className="quote-meta"><span>{quote.data.provider} · {quote.data.price_basis}</span><span>Source time {new Date(quote.data.source_timestamp).toLocaleString()}</span></div>
            <div className="quote-meta"><span>Bid {quote.data.bid == null ? "not supplied" : quoteAmount(quote.data.bid, quote.data.quote_currency)}</span><span>Ask {quote.data.ask == null ? "not supplied" : quoteAmount(quote.data.ask, quote.data.quote_currency)}</span></div>
            <button className="btn btn-secondary" onClick={() => saveWatchlist.mutate()} disabled={!selectedSymbol || saveWatchlist.isPending}><BookmarkPlus size={15}/>{saveWatchlist.isPending ? "Saving…" : "Add to my watchlist"}</button>
          </>}
        </div>
        <div className="panel market-chart-card"><div className="panel-header"><div><div className="eyebrow">HISTORICAL PRICE</div><h2>Provider candles</h2></div><select aria-label="Chart interval" value={interval} onChange={(event) => setInterval(event.target.value)}><option value="1day">Daily</option><option value="1h">Hourly</option><option value="15min">15 minutes</option><option value="5min">5 minutes</option></select></div>
          {candles.isLoading && <TableEmpty>Loading historical candles…</TableEmpty>}
          {candles.isError && <ErrorState message={errorText(candles.error)}/>}
          {candles.data?.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={candles.data.map((row) => ({ label: new Date(row.timestamp).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }), close: row.close }))} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}><defs><linearGradient id="marketFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#55d6be" stopOpacity={0.2}/><stop offset="100%" stopColor="#55d6be" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#ffffff0d" vertical={false}/><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#718096", fontSize: 10 }}/><YAxis domain={["auto", "auto"]} tickLine={false} axisLine={false} tick={{ fill: "#718096", fontSize: 10 }} width={55}/><Tooltip contentStyle={{ background: "#111a29", border: "1px solid #263246", borderRadius: 8, color: "#e8edf5" }} formatter={(value) => quoteAmount(Number(value), quote.data?.quote_currency ?? "")}/><Area type="monotone" dataKey="close" stroke="#55d6be" strokeWidth={2} fill="url(#marketFill)"/></AreaChart></ResponsiveContainer></div> : !candles.isLoading && !candles.isError && <TableEmpty>No historical candles were returned.</TableEmpty>}
        </div>
      </div>
      {feedback && <div className="inline-message" role="status">{feedback}</div>}
    </section>
    <section className="panel section-gap"><div className="panel-header"><div><div className="eyebrow">PRIVATE TO THIS ACCOUNT</div><h2>My watchlist</h2></div></div>
      {watchlist.isError && <ErrorState message={errorText(watchlist.error)}/>}
      {!watchlist.data?.length ? <TableEmpty>Save a searched instrument to build your account-scoped watchlist.</TableEmpty> : <div className="data-table"><div className="table-row table-head"><span>MARKET / INSTRUMENT</span><span>CURRENCY</span><span>ACTION</span></div>{watchlist.data.map((item) => <div className="table-row" key={`${item.market_type}-${item.symbol}`}><span className="instrument"><button className="watchlist-symbol" onClick={() => { changeMarket(item.market_type); setSearch(item.symbol); setSubmittedSearch(item.symbol); setSelectedSymbol(item.symbol); }}>{item.symbol}</button><small>{item.name}</small></span><span className="mono">{item.quote_currency}</span><span><button className="icon-button" aria-label={`Remove ${item.symbol}`} onClick={() => removeWatchlist.mutate(item)}><Trash2 size={14}/></button></span></div>)}</div>}
    </section>
  </>;
}

function PaperPage() {
  const portfolio = usePortfolio();
  const client = useQueryClient();
  const [marketType, setMarketType] = useState<MarketType>("EQUITY");
  const [search, setSearch] = useState("NIFTYBEES");
  const [submittedSearch, setSubmittedSearch] = useState("NIFTYBEES");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [message, setMessage] = useState("");
  const instruments = useQuery({ queryKey: ["paper-instruments", marketType, submittedSearch], queryFn: () => api<MarketInstrument[]>(marketSearchPath(marketType, submittedSearch)), enabled: Boolean(submittedSearch) });
  useEffect(() => {
    const rows = instruments.data ?? [];
    if (!rows.some((row) => row.symbol === selectedSymbol)) setSelectedSymbol(rows[0]?.symbol ?? "");
  }, [instruments.data, selectedSymbol]);
  const quote = useQuery({ queryKey: ["paper-quote", marketType, selectedSymbol], queryFn: () => api<MarketQuote>(marketQuotePath(marketType, selectedSymbol)), enabled: Boolean(selectedSymbol), retry: false });
  const canPaperTrade = quote.data?.status === "LIVE" || quote.data?.metadata.synthetic === true;
  const trade = useMutation({
    mutationFn: (order: { market_type: MarketType; symbol: string; side: "buy" | "sell"; quantity: number }) => api<Trade>("/api/v1/trades", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(order) }),
    onSuccess: (result) => { setMessage(`${result.side.toUpperCase()} ${result.quantity} ${result.quantity_unit ?? "shares"} of ${result.symbol} simulated at ${result.price}.`); void client.invalidateQueries({ queryKey: ["portfolio"] }); void client.invalidateQueries({ queryKey: ["performance"] }); void client.invalidateQueries({ queryKey: ["portfolio-history"] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  function changeMarket(value: MarketType) {
    const initialSearch = value === "EQUITY" ? "NIFTYBEES" : "EUR/USD";
    setMarketType(value); setSearch(initialSearch); setSubmittedSearch(initialSearch); setSelectedSymbol(""); setMessage("");
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const quantity = Number(form.get("quantity"));
    const side = String(form.get("side")) as "buy" | "sell";
    if (!Number.isSafeInteger(quantity) || quantity < 1) { setMessage("Enter a positive whole number of shares or base-currency units."); return; }
    if (!selectedSymbol || !canPaperTrade) { setMessage("A current, provider-listed quote is required before a simulated order."); return; }
    const quoteText = quote.data?.metadata.synthetic ? "local synthetic demo price" : "fresh provider quote";
    if (!window.confirm(`Place a virtual ${side.toUpperCase()} for ${quantity} ${selectedSymbol} using the ${quoteText}? Funds are virtual INR and no broker will be contacted.`)) return;
    setMessage("");
    trade.mutate({ market_type: marketType, symbol: selectedSymbol, side, quantity });
  }
  const p = portfolio.data;
  return <>
    <PageTitle eyebrow="VIRTUAL EXECUTION" title="Paper trading" subtitle="The simulator uses one virtual INR account for NSE/BSE equities and selected FX pairs. No broker connection exists."/>
    <div className="simulation-banner"><ShieldCheck size={17}/><div><b>Virtual money only</b><span>Starting virtual cash: {money(p?.starting_cash ?? 100000)}. Positions, orders, and watchlists are isolated to this signed-in user.</span></div><span className="banner-badge">NO LIVE TRADING</span></div>
    <section className="trade-layout"><article className="panel"><div className="eyebrow">NEW SIMULATED ORDER</div><h2>Place virtual order</h2>
      <div className="segmented market-toggle" role="group" aria-label="Order market type"><button className={marketType === "EQUITY" ? "selected" : ""} onClick={() => changeMarket("EQUITY")}>NSE / BSE equity</button><button className={marketType === "FOREX" ? "selected" : ""} onClick={() => changeMarket("FOREX")}>Forex</button></div>
      <form className="order-form" onSubmit={submit}>
        <label>Find instrument<input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); setSelectedSymbol(""); setSubmittedSearch(search.trim()); } }} placeholder={marketType === "EQUITY" ? "Symbol or company name" : "EUR/USD"} maxLength={50}/></label>
        <button className="btn btn-secondary instrument-search-button" type="button" onClick={() => { setSelectedSymbol(""); setSubmittedSearch(search.trim()); }} disabled={!search.trim() || instruments.isFetching}><Search size={15}/>{instruments.isFetching ? "Searching…" : "Search"}</button>
        <label className="instrument-select-label">Provider-listed instrument<select value={selectedSymbol} onChange={(event) => setSelectedSymbol(event.target.value)} disabled={!instruments.data?.length}>{(instruments.data ?? []).map((instrument) => <option key={instrument.symbol} value={instrument.symbol}>{instrument.symbol} · {instrument.name}</option>)}</select></label>
        {instruments.isError && <div className="form-error"><ErrorState message={errorText(instruments.error)}/></div>}
        <div className="quote-preview"><b>{quote.data ? quoteAmount(quote.data.price, quote.data.quote_currency) : "Quote not available"}</b>{quote.data && <><MarketStatusBadge status={quote.data.status} synthetic={quote.data.metadata.synthetic === true}/><small>{quote.data.provider} · {quote.data.price_basis} · {new Date(quote.data.source_timestamp).toLocaleString()}</small></>}{quote.isError && <small>{errorText(quote.error)}</small>}</div>
        <label>Action<select name="side"><option value="buy">Buy</option><option value="sell">Sell</option></select></label>
        <label>{marketType === "FOREX" ? "Base-currency units" : "Shares"}<input name="quantity" type="number" min="1" max="10000000" step="1" defaultValue="1" required/></label>
        <button className="btn btn-primary" disabled={trade.isPending || !canPaperTrade}><Play size={15}/>{trade.isPending ? "Submitting…" : "Confirm simulated order"}</button>
      </form>
      {message && <div className={`inline-message ${trade.isError ? "error" : ""}`} role="status">{message}</div>}
      <p className="fine-print">Order value, fees, slippage, FX conversion, cash, and exposure are recorded in virtual INR. Synthetic demo quotes are visibly labeled and work only in local development. FX prices are composite midpoints and do not include a provider bid/ask spread.</p>
    </article><article className="panel"><div className="eyebrow">ACCOUNT SUMMARY · INR</div><h2>Virtual portfolio</h2><div className="account-summary"><span>Available cash</span><b>{money(p?.cash)}</b><span>Invested value</span><b>{money(p?.market_value)}</b><span>Virtual equity</span><b>{money(p?.equity)}</b></div></article></section>
    <section className="panel section-gap"><div className="panel-header"><div><div className="eyebrow">POSITIONS</div><h2>Open holdings</h2></div></div><HoldingsTable holdings={p?.holdings ?? []}/></section>
    <section className="panel section-gap"><div className="panel-header"><div><div className="eyebrow">AUDIT TRAIL</div><h2>Order history</h2></div></div><TradeTable trades={p?.recent_trades ?? []}/></section>
  </>;
}
function HoldingsTable({ holdings }: { holdings: Portfolio["holdings"] }) {
  if (!holdings.length) return <TableEmpty>No open positions in this virtual account.</TableEmpty>;
  return <div className="data-table"><div className="table-row table-head four"><span>SYMBOL</span><span>QUANTITY</span><span>AVG. ENTRY</span><span>UNREALIZED P&L · INR</span></div>{holdings.map((holding) => <div className="table-row four" key={`${holding.market_type}-${holding.symbol}`}><span className="instrument"><b>{holding.symbol}</b><small>{holding.market_type} · {holding.provider ?? "provider unavailable"}</small></span><span>{holding.quantity} {holding.quantity_unit ?? "shares"}</span><span>{quoteAmount(holding.average_cost, holding.quote_currency ?? "INR")}</span><span className={holding.unrealized_pnl >= 0 ? "positive" : "negative"}>{money(holding.unrealized_pnl)}</span></div>)}</div>;
}

const DEFAULT_STRATEGY: StrategyConfig = {enabled:false,min_confidence:0.65,max_event_age_hours:24,max_position_percent:5,max_portfolio_exposure_percent:50,cooldown_minutes:60,daily_loss_limit_percent:5};
function StrategyPage(){
  const saved=useQuery({queryKey:["strategy-config"],queryFn:()=>api<StrategyVersion>("/api/v1/strategy/config")});
  const versions=useQuery({queryKey:["strategy-versions"],queryFn:()=>api<StrategyVersion[]>("/api/v1/strategy/versions")});
  const [feedback,setFeedback]=useState("");
  const [preview,setPreview]=useState<StrategyPreview|null>(null);
  const config=saved.data?.config??DEFAULT_STRATEGY;
  const save=useMutation({mutationFn:(next:StrategyConfig)=>api<StrategyVersion>("/api/v1/strategy/config",{method:"PUT",body:JSON.stringify(next)}),onSuccess:(result)=>{setFeedback(`Saved strategy version ${result.version}.`);void saved.refetch();void versions.refetch();},onError:(error:Error)=>setFeedback(error.message)});
  const runPreview=useMutation({mutationFn:()=>api<StrategyPreview>("/api/v1/strategy/preview",{method:"POST",body:"{}"}),onSuccess:(result)=>{setPreview(result);setFeedback("Preview complete. No simulated orders were generated.");},onError:(error:Error)=>setFeedback(error.message)});
  function saveConfig(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget);save.mutate({enabled:data.get("enabled")==="on",min_confidence:Number(data.get("min_confidence")),max_event_age_hours:Number(data.get("max_event_age_hours")),max_position_percent:Number(data.get("max_position_percent")),max_portfolio_exposure_percent:Number(data.get("max_portfolio_exposure_percent")),cooldown_minutes:Number(data.get("cooldown_minutes")),daily_loss_limit_percent:Number(data.get("daily_loss_limit_percent"))});}
  return <><PageTitle eyebrow="VERSIONED RULE CONFIGURATION" title="Strategy lab" subtitle="Configure per-account news rules, then preview or opt in to the separate paper-only worker."/><div className="simulation-banner"><ShieldCheck size={17}/><div><b>Paper execution only</b><span>The separate worker is disabled unless STRATEGY_EXECUTION_ENABLED=true, this strategy is enabled, and the kill switch is off. Production execution is disabled in this build.</span></div><span className="banner-badge">VIRTUAL ONLY</span></div>
    {saved.isError&&<ErrorState message={errorText(saved.error)}/>}<div className="strategy-layout"><form className="panel strategy-form" onSubmit={saveConfig}><div className="eyebrow">RULE PARAMETERS · VERSION {saved.data?.version??0}</div><h2>News event filters</h2><label className="strategy-toggle"><input name="enabled" type="checkbox" defaultChecked={config.enabled}/> Enable this configuration for the development paper worker</label><label>Minimum confidence <span className="muted-copy">0.50–0.95</span><input name="min_confidence" type="number" min="0.5" max="0.95" step="0.01" defaultValue={config.min_confidence}/></label><label>Maximum event age · hours<input name="max_event_age_hours" type="number" min="1" max="168" step="1" defaultValue={config.max_event_age_hours}/></label><label>Max position size · % of virtual equity<input name="max_position_percent" type="number" min="0.1" max="25" step="0.1" defaultValue={config.max_position_percent}/></label><label>Max portfolio exposure · %<input name="max_portfolio_exposure_percent" type="number" min="0.1" max="90" step="0.1" defaultValue={config.max_portfolio_exposure_percent}/></label><label>Realized daily loss limit · % of starting cash<input name="daily_loss_limit_percent" type="number" min="0.1" max="20" step="0.1" defaultValue={config.daily_loss_limit_percent}/></label><label>Cooldown · minutes<input name="cooldown_minutes" type="number" min="0" max="1440" step="1" defaultValue={config.cooldown_minutes}/></label><div className="strategy-actions"><button className="btn btn-primary" disabled={save.isPending}>{save.isPending?"Saving…":"Save new version"}</button><button type="button" className="btn btn-secondary" disabled={runPreview.isPending} onClick={()=>runPreview.mutate()}>{runPreview.isPending?"Evaluating…":"Preview current news"}</button></div>{feedback&&<div className={`inline-message ${save.isError||runPreview.isError?"error":""}`} role="status">{feedback}</div>}</form>
      <article className="panel"><div className="eyebrow">VERSION HISTORY</div><h2>Saved configurations</h2>{(versions.data??[]).length?versions.data!.map(item=><div className="config-row" key={item.version}><span>Version {item.version}{item.config.enabled?" · worker opted in":" · paused"}</span><b>{item.updated_at?new Date(item.updated_at).toLocaleString():"—"}</b></div>):<TableEmpty>No saved strategy versions yet.</TableEmpty>}<p className="fine-print">The worker applies position size, exposure, realized daily-loss, cooldown, confidence, and event-age controls before any simulated order.</p></article></div>
      {preview&&<section className="panel section-gap"><div className="panel-header"><div><div className="eyebrow">{preview.strategy_version} · {preview.results.length} ARTICLES</div><h2>Rule evaluation</h2></div><span className="pill pill-muted">No orders generated</span></div>{preview.results.length===0?<TableEmpty>No provider headlines were available to evaluate.</TableEmpty>:<div className="strategy-results">{preview.results.map((item)=><article className="strategy-result" key={item.article_id}><div className="strategy-result-head"><b>{item.title}</b><span className={`signal-pill ${item.action.toLowerCase()}`}>{item.action}</span></div><small>{item.symbols.join(", ")} · confidence {(item.confidence*100).toFixed(0)}% · {item.age_minutes===null?"age unavailable":`${item.age_minutes.toFixed(0)} minutes old`}</small><p>{item.decision_reason}</p></article>)}</div>}</section>}
  </>;
}

function BacktestPage(){
  const [dataset,setDataset]=useState<Omit<HistoricalReplayRequest,"data_rights_confirmed">|null>(null);
  const [fileName,setFileName]=useState("");
  const [rightsConfirmed,setRightsConfirmed]=useState(false);
  const [feedback,setFeedback]=useState("");
  const replay=useMutation({mutationFn:()=>{
    if(!dataset)throw new Error("Choose a historical JSON dataset first.");
    return api<HistoricalReplay>("/api/v1/backtest/replay",{method:"POST",body:JSON.stringify({...dataset,data_rights_confirmed:true})});
  },onError:(error:Error)=>setFeedback(error.message),onSuccess:()=>setFeedback("")});
  async function selectDataset(event:React.ChangeEvent<HTMLInputElement>){
    const file=event.currentTarget.files?.[0];
    if(!file)return;
    replay.reset();setDataset(null);setRightsConfirmed(false);setFileName(file.name);setFeedback("");
    if(file.size>5_000_000){setFeedback("Choose a JSON file that is 5 MB or smaller.");return;}
    try{
      const value=JSON.parse(await file.text()) as Partial<HistoricalReplayRequest>;
      if(!Array.isArray(value.candles)||!Array.isArray(value.news))throw new Error("The JSON must contain candles and news arrays.");
      if(typeof value.starting_cash!=="number"||!Number.isFinite(value.starting_cash)||value.starting_cash<=0)throw new Error("The JSON must include a positive starting_cash amount in INR.");
      setDataset({dataset_name:typeof value.dataset_name==="string"&&value.dataset_name.trim()?value.dataset_name:file.name.replace(/\.json$/i,""),...(typeof value.strategy_version==="number"?{strategy_version:value.strategy_version}:{}),starting_cash:value.starting_cash,candles:value.candles,news:value.news});
    }catch(error){setFeedback(error instanceof Error?error.message:"The selected file is not valid JSON.");}
  }
  const result=replay.data;
  return <>
    <PageTitle eyebrow="STRATEGY RESEARCH" title="Historical backtesting" subtitle="Replay archived news and market candles in chronological order using virtual INR accounting."/>
    <div className="simulation-banner warning"><BookOpenText size={17}/><div><b>Only your supplied history is used</b><span>Results are not independently verified. No synthetic history, live headlines, market provider, broker, or stored portfolio is used by this replay.</span></div><span className="banner-badge">PAPER ONLY</span></div>
    <section className="panel backtest-upload section-gap">
      <div className="panel-header"><div><div className="eyebrow">HISTORICAL INPUT</div><h2>Load a rights-cleared dataset</h2></div><span className="pill pill-muted">Format: docs/BACKTEST_DATA_FORMAT.md</span></div>
      <p className="muted-copy">Upload JSON with timestamped OHLC candles and archived news publication times. The replay accepts up to 20,000 candles and 2,000 news events, with a 5 MB file limit.</p>
      <label className="file-picker"><FileUp size={18}/><span>{fileName||"Choose historical dataset (.json)"}</span><input type="file" accept="application/json,.json" onChange={(event)=>void selectDataset(event)} aria-label="Choose historical JSON dataset"/></label>
      {dataset&&<div className="dataset-summary"><span><b>{dataset.dataset_name}</b></span><span>{dataset.candles.length.toLocaleString()} candles</span><span>{dataset.news.length.toLocaleString()} news events</span><span>Starting cash {money(dataset.starting_cash)}</span></div>}
      <label className="rights-confirm"><input type="checkbox" checked={rightsConfirmed} onChange={(event)=>setRightsConfirmed(event.target.checked)}/><span>I have the right to use and replay this data, and understand the result reflects only the dataset I provided.</span></label>
      <div className="backtest-actions"><button className="btn btn-primary" disabled={!dataset||!rightsConfirmed||replay.isPending} onClick={()=>replay.mutate()}><Play size={15}/>{replay.isPending?"Replaying history…":"Run virtual replay"}</button><span>Nothing is saved to your paper portfolio.</span></div>
      {feedback&&<div className="inline-message error" role="alert">{feedback}</div>}
    </section>
    {result&&<>
      <section className="metrics-grid backtest-metrics">
        <Metric label="ENDING EQUITY" value={money(result.ending_equity_inr)} detail={`Starting at ${money(result.starting_cash_inr)}`} icon={WalletCards} tone="blue"/>
        <Metric label="TOTAL RETURN" value={`${result.return_percent.toFixed(2)}%`} detail={`Realized ${money(result.realized_pnl_inr)}`} icon={result.return_percent>=0?ArrowUpRight:ArrowDownRight} tone={result.return_percent>=0?"green":"purple"}/>
        <Metric label="MAX DRAWDOWN" value={`${result.max_drawdown_percent.toFixed(2)}%`} detail="Measured at every replay timestamp" icon={Activity}/>
        <Metric label="VIRTUAL FILLS" value={result.filled_trade_count.toLocaleString()} detail={`${result.rejected_signal_count} rejected · ${result.unfilled_signal_count} unfilled`} icon={BarChart3}/>
      </section>
      <section className="panel section-gap backtest-result"><div className="panel-header"><div><div className="eyebrow">REPLAYED EQUITY</div><h2>{result.dataset_name}</h2></div><span className="pill pill-muted">Strategy version {result.strategy_version} · {result.bar_count.toLocaleString()} bars</span></div>
        <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={result.equity_curve.map(point=>({label:new Date(point.timestamp).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"2-digit"}),equity:point.equity}))} margin={{top:12,right:14,left:0,bottom:0}}><defs><linearGradient id="backtestFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#55d6be" stopOpacity={0.24}/><stop offset="100%" stopColor="#55d6be" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#ffffff0d" vertical={false}/><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{fill:"#718096",fontSize:10}}/><YAxis domain={["auto","auto"]} tickLine={false} axisLine={false} tick={{fill:"#718096",fontSize:10}} tickFormatter={(value:number)=>`₹${Math.round(value/1000)}k`} width={48}/><Tooltip contentStyle={{background:"#111a29",border:"1px solid #263246",borderRadius:8,color:"#e8edf5"}} formatter={(value)=>money(Number(value))}/><Area type="monotone" dataKey="equity" stroke="#55d6be" strokeWidth={2.5} fill="url(#backtestFill)"/></AreaChart></ResponsiveContainer></div>
        <p className="chart-note">Virtual costs: {money(result.fees_inr)} fees and {money(result.slippage_inr)} slippage. {result.notice}</p>
      </section>
      <section className="panel section-gap"><div className="panel-header"><div><div className="eyebrow">SIMULATED EXECUTIONS</div><h2>Next-candle fills</h2></div></div>
        {result.trades.length?<div className="table-scroll"><table><thead><tr><th>Time</th><th>Instrument</th><th>Side</th><th>Units</th><th>Fill</th><th>Value (INR)</th><th>Fees</th></tr></thead><tbody>{result.trades.slice(0,30).map((trade,index)=><tr key={`${trade.timestamp}-${trade.symbol}-${index}`}><td>{new Date(trade.timestamp).toLocaleString("en-IN")}</td><td><b>{trade.symbol}</b><small>{trade.market_type}</small></td><td><span className={`side-tag ${trade.side}`}>{trade.side.toUpperCase()}</span></td><td>{trade.quantity.toLocaleString()} {trade.quantity_unit}</td><td>{trade.fill_price}</td><td>{money(trade.value_inr)}</td><td>{money(trade.fees_inr)}</td></tr>)}</tbody></table>{result.filled_trade_count>30&&<p className="chart-note">Showing the first 30 of {result.filled_trade_count.toLocaleString()} fills; response includes at most 1,000 fill rows.</p>}</div>:<div className="table-empty">No signal produced a valid virtual fill for this dataset.</div>}
      </section>
      <section className="panel section-gap"><div className="panel-header"><div><div className="eyebrow">DECISION AUDIT</div><h2>News decisions and risk checks</h2></div><span className="pill pill-muted">{result.signal_count.toLocaleString()} decisions</span></div>
        {result.decisions.length?<div className="decision-list">{result.decisions.slice(0,20).map((decision,index)=><article className="decision-row" key={`${decision.published_at}-${decision.symbol??"event"}-${index}`}><div><b>{decision.symbol??decision.title}</b><small>{new Date(decision.published_at).toLocaleString("en-IN")} · {decision.action}</small></div><span className={`decision-status ${decision.status}`}>{decision.status}</span><p>{decision.reason}</p></article>)}</div>:<div className="table-empty">No archived news was available during this candle range.</div>}
        {result.signal_count>20&&<p className="chart-note">Showing the first 20 decisions. The response contains at most 2,000 decision rows.</p>}
      </section>
    </>}
  </>;
}

function SettingsPage(){
  const client=useQueryClient();
  const [deletePassword,setDeletePassword]=useState("");
  const [feedback,setFeedback]=useState("");
  const health=useQuery({queryKey:["health"],queryFn:()=>api<{status:string;database:string}>("/api/v1/ready")});
  const news=useQuery({queryKey:["news-status"],queryFn:()=>api<{configured:boolean;production_authorized:boolean;message:string}>("/api/v1/news/status")});
  const marketStatus=useQuery({queryKey:["market-data-status"],queryFn:()=>api<MarketDataStatus>("/api/v1/markets/status")});
  const reset=useMutation({mutationFn:()=>api<Portfolio>("/api/v1/portfolio/reset",{method:"POST",body:JSON.stringify({confirmation:"RESET VIRTUAL PORTFOLIO"})}),onSuccess:()=>{setFeedback("Virtual portfolio reset to its starting balance. An audit record was retained.");void client.invalidateQueries();},onError:(error:Error)=>setFeedback(error.message)});
  const deletion=useMutation({mutationFn:()=>api<{status:string}>("/api/v1/auth/me",{method:"DELETE",body:JSON.stringify({password:deletePassword})}),onSuccess:async()=>{setCsrfToken("");const csrf=await api<{csrf_token:string}>("/api/v1/auth/csrf");setCsrfToken(csrf.csrf_token);client.setQueryData(["auth-session"],null);},onError:(error:Error)=>setFeedback(error.message)});
  function confirmReset(){if(window.confirm("Reset all virtual holdings and order history to the starting balance? This cannot be undone.")){setFeedback("");reset.mutate();}}
  function deleteAccount(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!window.confirm("Delete your account, sessions, portfolio, and stored orders? This cannot be undone."))return;setFeedback("");deletion.mutate();}
  return <><PageTitle eyebrow="SYSTEM CONFIGURATION" title="Settings & status" subtitle="Local application and provider readiness. No credential values are shown here."/><div className="settings-grid">
    <div className="panel"><div className="eyebrow">SERVICE HEALTH</div><h2>Backend & database</h2><div className="health-row"><span className={`health-light ${health.data?"healthy":""}`}/><b>{health.data?`${health.data.status} · ${health.data.database}`:health.isError?"Unavailable":"Checking"}</b></div><p className="muted-copy">{health.isError?errorText(health.error):"The readiness endpoint checks database connectivity."}</p></div>
    <div className="panel"><div className="eyebrow">DATA PROVIDERS</div><h2>Configuration state</h2><div className="config-row"><span>News feed</span><b>{news.data?.configured?"Backend provider configured":"Not configured"}</b></div><div className="config-row"><span>NSE/BSE equities</span><b>{marketStatus.data?.EQUITY.configured?"Read-only provider configured":"Unavailable"}</b></div><div className="config-row"><span>Forex composite</span><b>{marketStatus.data?.FOREX.configured?"Provider configured":"Unavailable"}</b></div><p className="muted-copy">{news.data?.message??"Provider status is unavailable."} {marketStatus.data?.EQUITY.message} {marketStatus.data?.FOREX.message} Provider credentials stay on the backend; configuration status does not verify the provider's live response or display-license terms.</p></div>
    <div className="panel"><div className="eyebrow">PAPER ACCOUNT</div><h2>Portfolio reset</h2><p className="muted-copy">Reset restores virtual cash to the starting balance, removes positions and order history, and records an audit event. This action requires confirmation.</p><button className="btn btn-danger" onClick={confirmReset} disabled={reset.isPending}>{reset.isPending?"Resetting…":"Reset virtual portfolio"}</button></div>
    <div className="panel"><div className="eyebrow">SECURITY</div><h2>Session protection</h2><p className="muted-copy">Passwords use Argon2id. Sessions are stored server-side, revocable, HttpOnly, and protected by CSRF tokens. Password reset and email verification need a configured delivery provider and are not claimed as active.</p></div>
    <div className="panel danger-panel"><div className="eyebrow">ACCOUNT DELETION</div><h2>Delete account and data</h2><p className="muted-copy">This permanently removes your sessions, virtual portfolio, positions, snapshots, orders, and strategy settings. A non-identifying audit event is retained.</p><form className="delete-form" onSubmit={deleteAccount}><label>Confirm with your password<input type="password" autoComplete="current-password" value={deletePassword} onChange={event=>setDeletePassword(event.target.value)} required/></label><button className="btn btn-danger" disabled={deletion.isPending}>{deletion.isPending?"Deleting…":"Delete account permanently"}</button></form></div>
  </div>{feedback&&<div className="inline-message" role="status">{feedback}</div>}</>;
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: AuthUser, csrf: string) => void }) {
  const [mode, setMode] = useState<"login"|"register">("login");
  const [message, setMessage] = useState("");
  const mutation=useMutation({mutationFn:async(values:{email:string;password:string})=>api<{user:AuthUser;csrf_token:string}>(`/api/v1/auth/${mode}`,{method:"POST",body:JSON.stringify(values)}),onSuccess:(result)=>onAuthenticated(result.user,result.csrf_token),onError:(error:Error)=>setMessage(error.message)});
  function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=new FormData(event.currentTarget);mutation.mutate({email:String(form.get("email")),password:String(form.get("password"))});}
  return <div className="auth-screen"><div className="auth-card"><div className="brand auth-brand"><div className="brand-symbol">G<span>.</span></div><div><b>GLOBAL SIGNALS</b><small>SIMULATED MARKET RESEARCH</small></div></div><div className="eyebrow">PAPER TRADING WORKSPACE</div><h1>{mode==="login"?"Welcome back":"Create your account"}</h1><p className="muted-copy">{mode==="login"?"Sign in to your isolated virtual portfolio.":"Create a secure account with a virtual-only trading portfolio."}</p><form className="auth-form" onSubmit={submit}><label>Email address<input type="email" name="email" autoComplete="email" maxLength={254} required/></label><label>Password<input type="password" name="password" autoComplete={mode==="login"?"current-password":"new-password"} minLength={12} maxLength={128} required/><small>Use at least 12 characters.</small></label><button className="btn btn-primary" disabled={mutation.isPending}>{mutation.isPending?"Please wait…":mode==="login"?"Sign in":"Create account"}</button></form>{message&&<div className="inline-message error" role="alert">{message}</div>}<button className="auth-switch" onClick={()=>{setMessage("");setMode(mode==="login"?"register":"login");}}>{mode==="login"?"New to Global Signals? Create an account":"Already registered? Sign in"}</button><div className="auth-note"><ShieldCheck size={15}/> Simulation only. No broker credentials are requested or used.</div><p className="reset-note">Password reset email is unavailable until an authorized email provider is configured.</p></div></div>;
}

function SessionGate(){
  const queryClient=useQueryClient();
  const session=useQuery({queryKey:["auth-session"],queryFn:async()=>{const csrf=await api<{csrf_token:string}>("/api/v1/auth/csrf");setCsrfToken(csrf.csrf_token);try{return (await api<{user:AuthUser}>("/api/v1/auth/me")).user;}catch(error){if(error instanceof Error&&"status" in error&&(error as Error&{status:number}).status===401)return null;throw error;}}});
  const logout=useMutation({mutationFn:()=>api("/api/v1/auth/logout",{method:"POST",body:"{}"}),onSuccess:async()=>{setCsrfToken("");const csrf=await api<{csrf_token:string}>("/api/v1/auth/csrf");setCsrfToken(csrf.csrf_token);queryClient.setQueryData(["auth-session"],null);}});
  if(session.isPending)return <div className="auth-loading">Loading secure session…</div>;
  if(session.isError)return <div className="auth-loading"><ErrorState message={errorText(session.error)}/><button className="btn btn-secondary" onClick={()=>void session.refetch()}>Retry connection</button></div>;
  if(!session.data)return <AuthScreen onAuthenticated={(user,csrf)=>{setCsrfToken(csrf);queryClient.setQueryData(["auth-session"],user);}}/>;
  return <Shell user={session.data} onLogout={()=>logout.mutate()}/>;
}

export default function App(){return <SessionGate/>;}
