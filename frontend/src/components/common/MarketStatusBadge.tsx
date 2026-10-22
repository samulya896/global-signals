export function MarketStatusBadge({
  status,
  synthetic,
}: {
  status?: string;
  synthetic?: boolean;
}) {
  const label = synthetic ? "SYNTHETIC DEMO" : status ?? "UNAVAILABLE";
  return (
    <span className={`pill ${status === "LIVE" || synthetic ? "pill-green" : "pill-muted"}`}>
      {label}
    </span>
  );
}
