import type { Portfolio } from "../../lib/api";
import { money, quoteAmount } from "../../lib/formatters";
import { TableEmpty } from "../common/TableEmpty";

export function HoldingsTable({ holdings }: { holdings: Portfolio["holdings"] }) {
  if (!holdings.length) {
    return <TableEmpty>No open positions in this virtual account.</TableEmpty>;
  }
  return (
    <div className="data-table">
      <div className="table-row table-head four">
        <span>SYMBOL</span>
        <span>QUANTITY</span>
        <span>AVG. ENTRY</span>
        <span>UNREALIZED P&L · INR</span>
      </div>
      {holdings.map((holding) => (
        <div className="table-row four" key={`${holding.market_type}-${holding.symbol}`}>
          <span className="instrument">
            <b>{holding.symbol}</b>
            <small>
              {holding.market_type} · {holding.provider ?? "provider unavailable"}
            </small>
          </span>
          <span>
            {holding.quantity} {holding.quantity_unit ?? "shares"}
          </span>
          <span>{quoteAmount(holding.average_cost, holding.quote_currency ?? "INR")}</span>
          <span className={holding.unrealized_pnl >= 0 ? "positive" : "negative"}>
            {money(holding.unrealized_pnl)}
          </span>
        </div>
      ))}
    </div>
  );
}
