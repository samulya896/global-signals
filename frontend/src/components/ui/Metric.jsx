export function Metric({ label, value, detail }) {
  return (
    <div className="metric-card">
      <div className="metric-head">
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
