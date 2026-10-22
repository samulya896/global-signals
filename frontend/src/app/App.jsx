import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isApiErrorStatus, setCsrfToken, api } from "../lib/api";
import { Shell } from "../components/layout/Shell";
import { AuthScreen } from "../features/auth/AuthPage";
import { ErrorState } from "../components/feedback/ErrorState";
import { RouteErrorBoundary } from "../components/feedback/RouteErrorBoundary";
import { AppRoutes } from "./routes.jsx";
function SessionGate() {
  const location = useLocation();
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["auth-session"],
    queryFn: async () => {
      const csrf = await api("/api/v1/auth/csrf");
      setCsrfToken(csrf.csrf_token);
      try {
        return (await api("/api/v1/auth/me")).user;
      } catch (error) {
        if (isApiErrorStatus(error, 401)) return null;
        throw error;
      }
    },
  });
  const logout = useMutation({
    mutationFn: () =>
      api("/api/v1/auth/logout", { method: "POST", body: "{}" }),
    onSuccess: async () => {
      setCsrfToken("");
      const csrf = await api("/api/v1/auth/csrf");
      setCsrfToken(csrf.csrf_token);
      queryClient.setQueryData(["auth-session"], null);
    },
  });
  if (session.isPending)
    return (
      <div className="auth-loading" role="status" aria-live="polite">
        Loading secure session…
      </div>
    );
  if (session.isError)
    return (
      <div className="auth-loading">
        <ErrorState
          message={session.error.message ?? "Service is unavailable"}
        />
        <button
          className="btn btn-secondary"
          onClick={() => void session.refetch()}
        >
          Retry connection
        </button>
      </div>
    );
  if (!session.data)
    return (
      <AuthScreen
        onAuthenticated={(user, csrf) => {
          setCsrfToken(csrf);
          queryClient.setQueryData(["auth-session"], user);
        }}
      />
    );
  return (
    <Shell user={session.data} onLogout={() => logout.mutate()}>
      <RouteErrorBoundary key={location.pathname}>
        <AppRoutes />
      </RouteErrorBoundary>
    </Shell>
  );
}
export default function App() {
  return <SessionGate />;
}
