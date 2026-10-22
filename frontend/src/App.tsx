import { Route, Routes } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { setCsrfToken, api } from "./lib/api";
import type { AuthUser } from "./lib/api";
import { Shell } from "./components/layout/Shell";
import { AuthScreen } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";
import { NewsPage } from "./pages/NewsPage";
import { MarketsPage } from "./pages/MarketsPage";
import { PaperPage } from "./pages/PaperPage";
import StrategyPage from "./pages/StrategyPage";
import BacktestPage from "./pages/BacktestPage";
import SettingsPage from "./pages/SettingsPage";
import { ErrorState } from "./components/common/ErrorState";

function errorText(error: Error | null) {
  return error?.message ?? "Service is unavailable";
}

function SessionGate() {
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["auth-session"],
    queryFn: async () => {
      const csrf = await api<{ csrf_token: string }>("/api/v1/auth/csrf");
      setCsrfToken(csrf.csrf_token);
      try {
        return (await api<{ user: AuthUser }>("/api/v1/auth/me")).user;
      } catch (error) {
        if (error instanceof Error && "status" in error && (error as any).status === 401) return null;
        throw error;
      }
    },
  });
  const logout = useMutation({
    mutationFn: () => api("/api/v1/auth/logout", { method: "POST", body: "{}" }),
    onSuccess: async () => {
      setCsrfToken("");
      const csrf = await api<{ csrf_token: string }>("/api/v1/auth/csrf");
      setCsrfToken(csrf.csrf_token);
      queryClient.setQueryData(["auth-session"], null);
    },
  });

  if (session.isPending) return <div className="auth-loading">Loading secure session…</div>;
  if (session.isError)
    return (
      <div className="auth-loading">
        <ErrorState message={errorText(session.error)} />
        <button className="btn btn-secondary" onClick={() => void session.refetch()}>
          Retry connection
        </button>
      </div>
    );
  if (!session.data) return <AuthScreen onAuthenticated={(user, csrf) => { setCsrfToken(csrf); queryClient.setQueryData(["auth-session"], user); }} />;

  return (
    <Shell user={session.data} onLogout={() => logout.mutate()}>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/markets" element={<MarketsPage />} />
        <Route path="/paper" element={<PaperPage />} />
        <Route path="/strategy" element={<StrategyPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Shell>
  );
}

export default function App() {
  return <SessionGate />;
}
