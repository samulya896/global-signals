import { formatMoney } from "./api";
import type { MarketType } from "./api";

export function money(value?: number): string {
  return formatMoney(value ?? 0);
}

export function errorText(error: Error | null): string {
  return error?.message ?? "Service is unavailable";
}

export function quoteAmount(value: number, currency: string): string {
  return currency === "INR"
    ? money(value)
    : `${new Intl.NumberFormat("en-US", {
        minimumFractionDigits: currency === "JPY" ? 3 : 5,
        maximumFractionDigits: currency === "JPY" ? 3 : 5,
      }).format(value)} ${currency}`;
}

export function marketSearchPath(marketType: MarketType, query: string): string {
  const params = new URLSearchParams({ market_type: marketType, q: query, limit: "20" });
  return `/api/v1/markets/instruments?${params.toString()}`;
}

export function marketQuotePath(marketType: MarketType, symbol: string): string {
  const params = new URLSearchParams({ market_type: marketType, symbol });
  return `/api/v1/markets/quote?${params.toString()}`;
}
