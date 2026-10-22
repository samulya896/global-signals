// Strategy page refactored for compilation while preserving core functionality
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { PageTitle } from "../components/common/PageTitle";
import { ErrorState } from "../components/common/ErrorState";
import { api } from "../lib/api";
import type { StrategyConfig, StrategyVersion, StrategyPreview } from "../lib/api";

function errorText(error: Error | null) {
  return error?.message ?? "Service is unavailable";
}

const DEFAULT_STRATEGY: StrategyConfig = {
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
    queryFn: () => api<StrategyVersion>("/api/v1/strategy/config"),
  });
  const versions = useQuery({
    queryKey: ["strategy-versions"],
    queryFn: () => api<StrategyVersion[]>("/api/v1/strategy/versions"),
  });
  const [feedback, setFeedback] = useState("");
  const [preview, setPreview] = useState<StrategyPreview | null>(null);
  const config = saved.data?.config ?? DEFAULT_STRATEGY;

  const save = useMutation({
    mutationFn: (next: StrategyConfig) =>
      api<StrategyVersion>("/api/v1/strategy/config", { method: "PUT", body: JSON.stringify(next) }),
    onSuccess: result => {
      setFeedback(`Saved strategy version ${result.version}.`);
      void saved.refetch();
      void versions.refetch();
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const runPreview = useMutation({
    mutationFn: () =>
      api<StrategyPreview>("/api/v1/strategy/preview", { method: "POST", body: "{}" }),
    onSuccess: result => {
      setPreview(result);
      setFeedback("Preview complete. No simulated orders were generated.");
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  function saveConfig(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    save.mutate({
      enabled: data.get("enabled") === "on",
      min_confidence: Number(data.get("min_confidence")),
      max_event_age_hours: Number(data.get("max_event_age_hours")),
      max_position_percent: Number(data.get("max_position_percent")),
      max_portfolio_exposure_percent: Number(data.get("max_portfolio_exposure_percent")),
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
      <div className="simulation-banner">
        <ShieldCheck size={17} />
        <div><b>Paper execution only</b></div>
        <span className="banner-badge">VIRTUAL ONLY</span>
      </div>
      {saved.isError && <ErrorState message={errorText(saved.error)} />}
      <form className="panel strategy-form" onSubmit={saveConfig} style={{ padding: "1rem" }}>
        <div><strong>RULE PARAMETERS · VERSION {saved.data?.version ?? 0}</strong></div>
        <label>
          <input name="enabled" type="checkbox" defaultChecked={config.enabled} /> Enable this configuration
        </label>
        <label>Min confidence
          <input name="min_confidence" type="number" min="0.5" max="0.95" step="0.01" defaultValue={config.min_confidence} />
        </label>
        <label>Max event age (hours)
          <input name="max_event_age_hours" type="number" min="1" max="168" defaultValue={config.max_event_age_hours} />
        </label>
        <label>Max position %
          <input name="max_position_percent" type="number" min="0.1" max="25" step="0.1" defaultValue={config.max_position_percent} />
        </label>
        <label>Max portfolio exposure %
          <input name="max_portfolio_exposure_percent" type="number" min="0.1" max="90" step="0.1" defaultValue={config.max_portfolio_exposure_percent} />
        </label>
        <label>Daily loss limit %
          <input name="daily_loss_limit_percent" type="number" min="0.1" max="20" step="0.1" defaultValue={config.daily_loss_limit_percent} />
        </label>
        <label>Cooldown minutes
          <input name="cooldown_minutes" type="number" min="0" max="1440" defaultValue={config.cooldown_minutes} />
        </label>
        <div style={{ marginTop: "0.5rem" }}>
          <button type="submit" disabled={save.isPending}> {save.isPending ? "Saving…" : "Save new version"} </button>
          <button type="button" disabled={runPreview.isPending} onClick={() => runPreview.mutate()} style={{ marginLeft: "0.5rem" }}>
            {runPreview.isPending ? "Evaluating…" : "Preview current news"}
          </button>
        </div>
        {feedback && <div className="inline-message" role="status">{feedback}</div>}
      </form>
      {preview && (
        <div className="preview-section" style={{ marginTop: "1rem", padding: "1rem", border: "1px solid #ddd" }}>
          <h3>Preview (Version {preview.strategy_version})</h3>
          <p>{preview.results.length} articles evaluated.</p>
        </div>
      )}
    </>
  );
}
