import { money } from "../../lib/formatters";
import { TableEmpty } from "../feedback/TableEmpty";
export function TradeTable({ trades }) {
  if (!trades.length) {
    return (
      <TableEmpty>
        No simulated orders yet. Visit Paper trading to place a virtual order.
      </TableEmpty>
    );
  }
  return (
    <div className="data-table">
      <div className="table-row table-head">
        <span>Order</span>
        <span>Value · INR</span>
        <span>Record</span>
      </div>
      {trades.slice(0, 5).map((t, i) => (
        <div className="table-row" key={`${t.timestamp}-${i}`}>
          <span className="instrument">
            <b>
              {t.side.toUpperCase()} {t.symbol}
            </b>
            <small>
              {t.quantity} {t.quantity_unit ?? "shares"} ·{" "}
              {new Date(t.timestamp).toLocaleString()}
            </small>
            <small>
              Fee {money(t.fees)} · slippage {money(t.slippage)}
            </small>
          </span>
          <span className="mono">{money(t.value_inr ?? t.value)}</span>
          <span className="trade-record">Virtual</span>
        </div>
      ))}
    </div>
  );
}
