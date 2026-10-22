import { formatMoney } from "./api";
export function money(value) {
  return formatMoney(value ?? 0);
}
export function errorText(error) {
  return error?.message ?? "Service is unavailable";
}
export function quoteAmount(value, currency) {
  return currency === "INR"
    ? money(value)
    : `${new Intl.NumberFormat("en-US", {
        minimumFractionDigits: currency === "JPY" ? 3 : 5,
        maximumFractionDigits: currency === "JPY" ? 3 : 5,
      }).format(value)} ${currency}`;
}
export function marketSearchPath(marketType, query) {
  const params = new URLSearchParams({
    market_type: marketType,
    q: query,
    limit: "20",
  });
  return `/api/v1/markets/instruments?${params.toString()}`;
}
export function marketQuotePath(marketType, symbol) {
  const params = new URLSearchParams({ market_type: marketType, symbol });
  return `/api/v1/markets/quote?${params.toString()}`;
}
