import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, setCsrfToken } from "../../lib/api";
import { errorText } from "../../lib/formatters";
import { PageTitle } from "../../components/ui/PageTitle";
export default function SettingsPage() {
  const client = useQueryClient();
  const [deletePassword, setDeletePassword] = useState("");
  const [feedback, setFeedback] = useState("");
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api("/api/v1/ready"),
  });
  const news = useQuery({
    queryKey: ["news-status"],
    queryFn: () => api("/api/v1/news/status"),
  });
  const marketStatus = useQuery({
    queryKey: ["market-data-status"],
    queryFn: () => api("/api/v1/markets/status"),
  });
  const reset = useMutation({
    mutationFn: () =>
      api("/api/v1/portfolio/reset", {
        method: "POST",
        body: JSON.stringify({ confirmation: "RESET VIRTUAL PORTFOLIO" }),
      }),
    onSuccess: () => {
      setFeedback(
        "Virtual portfolio reset to its starting balance. An audit record was retained.",
      );
      void client.invalidateQueries();
    },
    onError: (error) => setFeedback(error.message),
  });
  const deletion = useMutation({
    mutationFn: () =>
      api("/api/v1/auth/me", {
        method: "DELETE",
        body: JSON.stringify({ password: deletePassword }),
      }),
    onSuccess: async () => {
      setCsrfToken("");
      const csrf = await api("/api/v1/auth/csrf");
      setCsrfToken(csrf.csrf_token);
      client.setQueryData(["auth-session"], null);
    },
    onError: (error) => setFeedback(error.message),
  });
  function confirmReset() {
    if (
      window.confirm(
        "Reset all virtual holdings and order history to the starting balance? This cannot be undone.",
      )
    ) {
      setFeedback("");
      reset.mutate();
    }
  }
  function deleteAccount(event) {
    event.preventDefault();
    if (
      !window.confirm(
        "Delete your account, sessions, portfolio, and stored orders? This cannot be undone.",
      )
    )
      return;
    setFeedback("");
    deletion.mutate();
  }
  return (
    <>
      <PageTitle
        eyebrow="SYSTEM CONFIGURATION"
        title="Settings & status"
        subtitle="Local application and provider readiness. No credential values are shown here."
      />
      <div className="settings-grid">
        <div className="panel">
          <div className="eyebrow">SERVICE HEALTH</div>
          <h2>Backend & database</h2>
          <div className="health-row">
            <span className={`health-light ${health.data ? "healthy" : ""}`} />
            <b>
              {health.data
                ? `${health.data.status} · ${health.data.database}`
                : health.isError
                  ? "Unavailable"
                  : "Checking"}
            </b>
          </div>
          <p className="muted-copy">
            {health.isError
              ? errorText(health.error)
              : "The readiness endpoint checks database connectivity."}
          </p>
        </div>
        <div className="panel">
          <div className="eyebrow">DATA PROVIDERS</div>
          <h2>Configuration state</h2>
          <div className="config-row">
            <span>News feed</span>
            <b>
              {news.isPending
                ? "Checking…"
                : news.isError
                  ? "Unavailable"
                  : news.data.configured
                    ? "Backend provider configured"
                    : "Not configured"}
            </b>
          </div>
          <div className="config-row">
            <span>NSE/BSE equities</span>
            <b>
              {marketStatus.isPending
                ? "Checking…"
                : marketStatus.isError
                  ? "Unavailable"
                  : marketStatus.data.EQUITY.configured
                    ? "Read-only provider configured"
                    : "Not configured"}
            </b>
          </div>
          <div className="config-row">
            <span>Forex composite</span>
            <b>
              {marketStatus.isPending
                ? "Checking…"
                : marketStatus.isError
                  ? "Unavailable"
                  : marketStatus.data.FOREX.configured
                    ? "Provider configured"
                    : "Not configured"}
            </b>
          </div>
          <p className="muted-copy">
            {news.data?.message ??
              (news.isPending
                ? "Checking news provider status."
                : "News provider status is unavailable.")}{" "}
            {marketStatus.data?.EQUITY.message}{" "}
            {marketStatus.data?.FOREX.message} Provider credentials stay on the
            backend; configuration status does not verify the provider's live
            response or display-license terms.
          </p>
        </div>
        <div className="panel">
          <div className="eyebrow">PAPER ACCOUNT</div>
          <h2>Portfolio reset</h2>
          <p className="muted-copy">
            Reset restores virtual cash to the starting balance, removes
            positions and order history, and records an audit event. This action
            requires confirmation.
          </p>
          <button
            className="btn btn-danger"
            onClick={confirmReset}
            disabled={reset.isPending}
          >
            {reset.isPending ? "Resetting…" : "Reset virtual portfolio"}
          </button>
        </div>
        <div className="panel">
          <div className="eyebrow">SECURITY</div>
          <h2>Session protection</h2>
          <p className="muted-copy">
            Passwords use Argon2id. Sessions are stored server-side, revocable,
            HttpOnly, and protected by CSRF tokens. Password reset and email
            verification need a configured delivery provider and are not claimed
            as active.
          </p>
        </div>
        <div className="panel danger-panel">
          <div className="eyebrow">ACCOUNT DELETION</div>
          <h2>Delete account and data</h2>
          <p className="muted-copy">
            This permanently removes your sessions, virtual portfolio,
            positions, snapshots, orders, and strategy settings. A
            non-identifying audit event is retained.
          </p>
          <form className="delete-form" onSubmit={deleteAccount}>
            <label>
              Confirm with your password
              <input
                type="password"
                autoComplete="current-password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                required
              />
            </label>
            <button className="btn btn-danger" disabled={deletion.isPending}>
              {deletion.isPending ? "Deleting…" : "Delete account permanently"}
            </button>
          </form>
        </div>
        {feedback && (
          <div className="inline-message" role="status">
            {feedback}
          </div>
        )}
      </div>
    </>
  );
}
