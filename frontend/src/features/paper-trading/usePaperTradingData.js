import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { marketQuotePath, marketSearchPath } from "../../lib/formatters";

export function usePaperTradingData({
  marketType,
  submittedSearch,
  selectedSymbol,
}) {
  const portfolio = useQuery({
    queryKey: ["portfolio"],
    queryFn: () => api("/api/v1/portfolio"),
  });
  const instruments = useQuery({
    queryKey: ["paper-instruments", marketType, submittedSearch],
    queryFn: () => api(marketSearchPath(marketType, submittedSearch)),
    enabled: Boolean(submittedSearch),
  });
  const quote = useQuery({
    queryKey: ["paper-quote", marketType, selectedSymbol],
    queryFn: () => api(marketQuotePath(marketType, selectedSymbol)),
    enabled: Boolean(selectedSymbol),
    retry: false,
  });

  return { portfolio, instruments, quote };
}
