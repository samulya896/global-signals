import type { ReactNode } from "react";

export function TableEmpty({ children }: { children: ReactNode }) {
  return <div className="table-empty">{children}</div>;
}
