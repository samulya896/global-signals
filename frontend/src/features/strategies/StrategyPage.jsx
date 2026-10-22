// Strategy page refactored for compilation while preserving core functionality
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { PageTitle } from "../../components/ui/PageTitle";
import { ErrorState } from "../../components/feedback/ErrorState";
import { api } from "../../lib/api";
function errorText(error) {
  return error?.message ?? "Service is unavailable";
}
const DEFAULT_STRATEGY = {
  enabled: false,
  min_confidence: 0.65,
  max_event_age_hours: 24,
  max_position_percent: 5,
  max_portfolio_exposure_percent: 50,
  cooldown_minutes: 60,
  daily_loss_limit_percent: 5,
};
export default function StrategyPage() {
  const saved = useQuery({
    queryKey: ["strategy-config"],
    queryFn: () => api("/api/v1/strategy/config"),
  });
  const versions = useQuery({
    queryKey: ["strategy-versions"],
    queryFn: () => api("/api/v1/strategy/versions"),
  });
  const [feedback, setFeedback] = useState("");
  const [preview, setPreview] = useState(null);
  const config = saved.data?.config ?? DEFAULT_STRATEGY;
  const save = useMutation({
    mutationFn: (next) =>
      api("/api/v1/strategy/config", {
        method: "PUT",
        body: JSON.stringify(next),
      }),
    onSuccess: (result) => {
      setFeedback(`Saved strategy version ${result.version}.`);
      void saved.refetch();
      void versions.refetch();
    },
    onError: (err) => setFeedback(err.message),
  });
  const runPreview = useMutation({
    mutationFn: () =>
      api("/api/v1/strategy/preview", { method: "POST", body: "{}" }),
    onSuccess: (result) => {
      setPreview(result);
      setFeedback("Preview complete. No simulated orders were generated.");
    },
    onError: (err) => setFeedback(err.message),
  });
  function saveConfig(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    save.mutate({
      enabled: data.get("enabled") === "on",
      min_confidence: Number(data.get("min_confidence")),
      max_event_age_hours: Number(data.get("max_event_age_hours")),
      max_position_percent: Number(data.get("max_position_percent")),
      max_portfolio_exposure_percent: Number(
        data.get("max_portfolio_exposure_percent"),
      ),
      cooldown_minutes: Number(data.get("cooldown_minutes")),
      daily_loss_limit_percent: Number(data.get("daily_loss_limit_percent")),
    });
  }
  return (
    <>
      <PageTitle
        eyebrow="VERSIONED RULE CONFIGURATION"
        title="Strategy lab"
        subtitle="Configure per-account news rules, then preview or opt in to the separate paper-only worker."
      />
      {saved.isError && <ErrorState message={errorText(saved.error)} />}
      <form
        className="panel strategy-form strategy-config"
        onSubmit={saveConfig}
      >
        <header className="strategy-heading">
          <div>
            <span className="eyebrow">CONFIGURATION</span>
            <h2>Rule parameters</h2>
          </div>
          <span className="strategy-version">
            Version {saved.data?.version ?? 0}
          </span>
        </header>
        <label className="strategy-enabled">
          <input
            name="enabled"
            type="checkbox"
            defaultChecked={config.enabled}
          />{" "}
          Enable this configuration
        </label>
        <label>
          Min confidence
          <input
            name="min_confidence"
            type="number"
            min="0.5"
            max="0.95"
            step="0.01"
            defaultValue={config.min_confidence}
          />
        </label>
        <label>
          Max event age (hours)
          <input
            name="max_event_age_hours"
            type="number"
            min="1"
            max="168"
            defaultValue={config.max_event_age_hours}
          />
        </label>
        <label>
          Max position %
          <input
            name="max_position_percent"
            type="number"
            min="0.1"
            max="25"
            step="0.1"
            defaultValue={config.max_position_percent}
          />
        </label>
        <label>
          Max portfolio exposure %
          <input
            name="max_portfolio_exposure_percent"
            type="number"
            min="0.1"
            max="90"
            step="0.1"
            defaultValue={config.max_portfolio_exposure_percent}
          />
        </label>
        <label>
          Daily loss limit %
          <input
            name="daily_loss_limit_percent"
            type="number"
            min="0.1"
            max="20"
            step="0.1"
            defaultValue={config.daily_loss_limit_percent}
          />
        </label>
        <label>
          Cooldown minutes
          <input
            name="cooldown_minutes"
            type="number"
            min="0"
            max="1440"
            defaultValue={config.cooldown_minutes}
          />
        </label>
        <div className="strategy-actions">
          <button
            className="btn btn-primary"
            type="submit"
            disabled={save.isPending}
          >
            {" "}
            {save.isPending ? "Saving…" : "Save new version"}{" "}
          </button>
          <button
            className="btn btn-secondary"
            type="button"
            disabled={runPreview.isPending}
            onClick={() => runPreview.mutate()}
          >
            {runPreview.isPending ? "Evaluating…" : "Preview current news"}
          </button>
        </div>
        {feedback && (
          <div className="inline-message" role="status">
            {feedback}
          </div>
        )}
      </form>
      {preview && (
        <div className="panel preview-section">
          <div className="panel-header">
            <div>
              <span className="eyebrow">
                PREVIEW · VERSION {preview.strategy_version}
              </span>
              <h2>Current news evaluation</h2>
            </div>
            <span className="pill pill-muted">No orders generated</span>
          </div>
          <p>
            {preview.results.length} articles evaluated using the current
            configuration.
          </p>
        </div>
      )}
    </>
  );
}
