import type { Quote } from "../../lib/api";
import { quoteAmount } from "../../lib/formatters";
import { ErrorState } from "../common/ErrorState";
import { TableEmpty } from "../common/TableEmpty";

export function QuoteTable({
  quotes,
  loading,
  error,
}: {
  quotes: Quote[];
  loading?: boolean;
  error?: string;
}) {
  if (loading) return <TableEmpty>Loading simulated quotes…</TableEmpty>;
  if (error) return <ErrorState message={error} />;
  if (!quotes.length) return <TableEmpty>Quote data is unavailable.</TableEmpty>;
  return (
    <div className="data-table">
      <div className="table-row table-head">
        <span>INSTRUMENT</span>
        <span>PRICE</span>
        <span>DAILY CHANGE</span>
      </div>
      {quotes.map((q) => (
        <div className="table-row" key={q.symbol}>
          <span className="instrument">
            <b>{q.symbol}</b>
            <small>
              {q.provider ?? q.source}
              {q.status ? ` · ${q.status}` : ""}
            </small>
          </span>
          <span className="mono">
            {quoteAmount(q.price, q.quote_currency ?? q.currency ?? "INR")}
          </span>
          <span className={`change ${(q.change_percent ?? 0) >= 0 ? "positive" : "negative"}`}>
            {q.change_percent == null
              ? "—"
              : `${q.change_percent >= 0 ? "+" : ""}${q.change_percent.toFixed(2)}%`}
          </span>
        </div>
      ))}
    </div>
  );
}
