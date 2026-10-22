export function TableSkeleton({ rows = 4, columns = 3 }) {
  return (
    <div
      className="table-skeleton"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <span className="sr-only">Loading table data</span>
      {Array.from({ length: rows }, (_, row) => (
        <div className="table-skeleton-row" key={row}>
          {Array.from({ length: columns }, (_, column) => (
            <span className="loading-line" key={column} />
          ))}
        </div>
      ))}
    </div>
  );
}
