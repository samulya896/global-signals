import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { marketQuotePath, marketSearchPath } from "../../lib/formatters";

export function useMarketsData({
  marketType,
  submittedSearch,
  selectedSymbol,
  interval,
}) {
  const status = useQuery({
    queryKey: ["market-data-status"],
    queryFn: () => api("/api/v1/markets/status"),
  });
  const instruments = useQuery({
    queryKey: ["market-instruments", marketType, submittedSearch],
    queryFn: () => api(marketSearchPath(marketType, submittedSearch)),
    enabled: Boolean(submittedSearch),
  });
  const quote = useQuery({
    queryKey: ["market-quote", marketType, selectedSymbol],
    queryFn: () => api(marketQuotePath(marketType, selectedSymbol)),
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
      return api(`/api/v1/markets/candles?${params.toString()}`);
    },
    enabled: Boolean(selectedSymbol),
    staleTime: 60_000,
    retry: false,
  });
  const watchlist = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api("/api/v1/watchlist"),
  });

  return { status, instruments, quote, candles, watchlist };
}
