import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

export function useDashboardData() {
  const portfolio = useQuery({
    queryKey: ["portfolio"],
    queryFn: () => api("/api/v1/portfolio"),
  });
  const performance = useQuery({
    queryKey: ["performance"],
    queryFn: () => api("/api/v1/performance"),
  });
  const market = useQuery({
    queryKey: ["market"],
    queryFn: () => api("/api/v1/market"),
  });
  const signals = useQuery({
    queryKey: ["signals"],
    queryFn: () => api("/api/v1/signals"),
  });
  const history = useQuery({
    queryKey: ["portfolio-history"],
    queryFn: () => api("/api/v1/portfolio/history"),
  });

  return { portfolio, performance, market, signals, history };
}
