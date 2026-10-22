import { Activity, ArrowDownRight, ArrowUpRight } from "lucide-react";
import { ErrorState } from "../feedback/ErrorState";
import { TableEmpty } from "../feedback/TableEmpty";
import { TableSkeleton } from "../feedback/TableSkeleton";
export function SignalList({ signals, loading, error }) {
  if (loading) return <TableSkeleton rows={3} columns={3} />;
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
          <span className={`signal-pill ${s.action.toLowerCase()}`}>
            {s.action}
          </span>
        </div>
      ))}
    </div>
  );
}
