import type { ElementType } from "react";

export function Metric({
  label,
  value,
  detail,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  icon: ElementType;
  tone?: string;
}) {
  return (
    <div className="metric-card">
      <div className="metric-head">
        <span>{label}</span>
        <span className={`metric-icon ${tone}`}>
          <Icon size={16} />
        </span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
