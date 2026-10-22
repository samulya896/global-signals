import { Activity, ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { Signal } from "../../lib/api";
import { ErrorState } from "../common/ErrorState";
import { TableEmpty } from "../common/TableEmpty";

export function SignalList({
  signals,
  loading,
  error,
}: {
  signals: Signal[];
  loading?: boolean;
  error?: string;
}) {
  if (loading) return <TableEmpty>Analyzing available headlines…</TableEmpty>;
  if (error) return <ErrorState message={error} />;
  if (!signals.length) return <TableEmpty>No signals available.</TableEmpty>;
  return (
    <div className="signal-list">
      {signals.map((s, i) => (
        <div className="signal-row" key={`${s.title}-${i}`}>
          <span className={`signal-mark ${s.action.toLowerCase()}`}>
            {s.action === "BUY" ? (
              <ArrowUpRight size={16} />
            ) : s.action === "SELL" ? (
              <ArrowDownRight size={16} />
            ) : (
              <Activity size={15} />
            )}
          </span>
          <div className="signal-copy">
            <b>{s.title}</b>
            <small>
              {s.symbols.join(", ")} <span>·</span> {s.category} <span>·</span>{" "}
              {s.matched_keywords.join(", ") || "No matching terms"}
            </small>
          </div>
          <span className={`signal-pill ${s.action.toLowerCase()}`}>{s.action}</span>
        </div>
      ))}
    </div>
  );
}
