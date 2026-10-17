export type Holding = {
  market_type?: "EQUITY" | "FOREX";
  symbol: string;
  quantity: number;
  quantity_unit?: string;
  base_currency?: string | null;
  quote_currency?: string;
  average_cost: number;
  average_cost_inr?: number;
  price: number;
  market_value: number;
  market_value_quote?: number;
  unrealized_pnl: number;
  provider?: string;
  source_timestamp?: string;
  data_status?: DataStatus;
  conversion_rate_to_inr?: number;
};

export type Portfolio = {
  mode: "simulation";
  starting_cash: number;
  cash: number;
  market_value: number;
  equity: number;
  unrealized_pnl: number;
  holdings: Holding[];
  recent_trades: Trade[];
};

export type Trade = {
  market_type?: "EQUITY" | "FOREX";
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  quantity_unit?: string;
  price: number;
  quote_price: number;
  value: number;
  value_inr?: number;
  fees: number;
  slippage: number;
  realized_pnl: number;
  quote_currency?: string;
  base_currency?: string | null;
  conversion_rate_to_inr?: number;
  provider?: string;
  price_basis?: string;
  source_timestamp?: string | null;
  timestamp: string;
  status: "filled";
  mode: "simulation";
};

export type Quote = {
  symbol: string;
  price: number;
  change_percent: number | null;
  source: string;
  provider?: string;
  currency?: string;
  quote_currency?: string;
  status?: DataStatus;
  source_timestamp?: string;
};

export type MarketType = "EQUITY" | "FOREX";
export type DataStatus = "LIVE" | "DELAYED" | "HISTORICAL" | "UNAVAILABLE";

export type MarketInstrument = {
  market_type: MarketType;
  symbol: string;
  provider: string;
  name: string;
  exchange: string | null;
  base_currency: string | null;
  quote_currency: string;
  instrument_key: string | null;
  tick_size: number | null;
  metadata: Record<string, unknown>;
};

export type MarketQuote = {
  market_type: MarketType;
  provider: string;
  source: string;
  symbol: string;
  price: number;
  currency: string;
  base_currency: string | null;
  quote_currency: string;
  bid: number | null;
  ask: number | null;
  price_basis: string;
  source_timestamp: string;
  retrieved_at: string;
  status: DataStatus;
  market_status: string | null;
  change_percent: number | null;
  metadata: Record<string, unknown>;
};

export type MarketCandle = {
  market_type: MarketType;
  provider: string;
  symbol: string;
  interval: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  currency: string;
  status: DataStatus;
};

export type MarketDataStatus = Record<MarketType, {
  provider: string;
  configured: boolean;
  message: string;
}>;

export type WatchlistItem = {
  market_type: MarketType;
  symbol: string;
  name: string;
  base_currency: string | null;
  quote_currency: string;
  created_at: string;
};

export type PortfolioPoint = { recorded_at: string; equity: number };

export type Signal = {
  article_id: string;
  title: string;
  source: string | null;
  url: string | null;
  category: string;
  symbols: string[];
  action: "BUY" | "SELL" | "HOLD";
  sentiment: "positive" | "negative" | "neutral" | "uncertain";
  score: number;
  confidence: number;
  matched_keywords: string[];
  explanation: string;
  strategy_version: string;
  decision_at: string;
  published_at: string | null;
  retrieved_at: string | null;
  source_reliability: string;
};

export type Performance = {
  mode: string;
  starting_cash: number;
  equity: number;
  total_return: number;
  realized_pnl: number;
  unrealized_pnl: number;
  trade_count: number;
};

export type Backtest = {
  mode: string;
  days: number;
  starting_cash: number;
  ending_equity: number;
  return_percent: number;
  max_drawdown_percent: number;
  note: string;
};

export type HistoricalReplayRequest = {
  dataset_name: string;
  data_rights_confirmed: true;
  strategy_version?: number | null;
  starting_cash: number;
  candles: Array<{
    market_type: MarketType;
    symbol: string;
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    base_currency?: string | null;
    quote_currency: string;
  }>;
  news: Array<{
    title: string;
    description?: string;
    source?: string | null;
    url?: string | null;
    published_at: string;
  }>;
};

export type HistoricalReplay = {
  mode: "historical_replay_simulation";
  dataset_name: string;
  data_rights_attested: true;
  strategy_version: number;
  strategy_config: StrategyConfig;
  start_timestamp: string;
  end_timestamp: string;
  starting_cash_inr: number;
  ending_equity_inr: number;
  return_percent: number;
  max_drawdown_percent: number;
  cash_inr: number;
  realized_pnl_inr: number;
  fees_inr: number;
  slippage_inr: number;
  bar_count: number;
  signal_count: number;
  filled_trade_count: number;
  rejected_signal_count: number;
  unfilled_signal_count: number;
  equity_curve: Array<{ timestamp: string; equity: number }>;
  trades: Array<{
    timestamp: string;
    market_type: MarketType;
    symbol: string;
    side: "buy" | "sell";
    quantity: number;
    quantity_unit: string | null;
    news_title: string;
    fill_price: number;
    quote_currency: string;
    conversion_rate_to_inr: number;
    value_inr: number;
    fees_inr: number;
    slippage_inr: number;
    realized_pnl_inr: number;
  }>;
  decisions: Array<{
    title: string;
    published_at: string;
    symbol?: string;
    action: string;
    confidence?: number;
    status: "filled" | "rejected" | "unfilled" | "queued";
    reason: string;
    fill_timestamp?: string;
    quantity?: number;
    fill_price?: number;
  }>;
  notice: string;
};

export type AuthUser = { id: string; email: string; created_at: string };
export type StrategyConfig = {
  enabled: boolean;
  min_confidence: number;
  max_event_age_hours: number;
  max_position_percent: number;
  max_portfolio_exposure_percent: number;
  cooldown_minutes: number;
  daily_loss_limit_percent: number;
};
export type StrategyVersion = { version: number; config: StrategyConfig; updated_at: string | null };
export type StrategyResult = Signal & {
  accepted: boolean;
  decision_reason: string;
  age_minutes: number | null;
};
export type StrategyPreview = {
  mode: "read-only strategy preview";
  strategy_name: string;
  strategy_version: string;
  config: StrategyConfig;
  decision_at: string;
  orders_generated: false;
  results: StrategyResult[];
};

let csrfToken = "";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
export function setCsrfToken(token: string) { csrfToken = token; }

class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string"
      ? body.detail
      : Array.isArray(body.detail)
        ? body.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(" ") || `Request failed (${response.status})`
        : `Request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

export const formatMoney = (amount: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(amount);

export function isSafeArticleUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}
