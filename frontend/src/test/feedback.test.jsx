import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import React from "react";
import { ErrorState } from "../components/feedback/ErrorState";
import { PageLoading } from "../components/feedback/PageLoading";
import { TableSkeleton } from "../components/feedback/TableSkeleton";

afterEach(cleanup);

describe("shared feedback components", () => {
  it("announces page loading to assistive technology", () => {
    render(<PageLoading />);
    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-busy")).toBe("true");
    expect(status.textContent).toContain("Loading page");
  });

  it("renders the requested table skeleton row count", () => {
    const { container } = render(<TableSkeleton rows={4} columns={3} />);
    expect(screen.getByRole("status").getAttribute("aria-busy")).toBe("true");
    expect(container.querySelectorAll(".table-skeleton-row")).toHaveLength(4);
  });

  it("exposes errors as alerts", () => {
    render(<ErrorState message="Market data is unavailable." />);
    expect(screen.getByRole("alert").textContent).toContain(
      "Market data is unavailable.",
    );
  });
});
