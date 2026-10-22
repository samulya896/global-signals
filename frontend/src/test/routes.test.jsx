import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import { AppRoutes } from "../app/routes";
import { Shell } from "../components/layout/Shell";

const emptyPortfolio = {
  mode: "simulation",
  starting_cash: 100000,
  cash: 100000,
  market_value: 0,
  equity: 100000,
  unrealized_pnl: 0,
  holdings: [],
  recent_trades: [],
};

function apiResponse(path) {
  if (path.endsWith("/portfolio/history")) return [];
  if (path.endsWith("/portfolio")) return emptyPortfolio;
  if (path.endsWith("/performance"))
    return { total_return: 0, realized_pnl: 0, unrealized_pnl: 0 };
  if (path.endsWith("/market")) return [];
  if (path.endsWith("/signals") || path.endsWith("/news/live")) return [];
  if (path.endsWith("/news/status"))
    return {
      configured: false,
      production_authorized: false,
      message: "Not configured",
    };
  if (path.includes("/markets/status"))
    return {
      EQUITY: {
        provider: "Test",
        configured: false,
        message: "Not configured",
      },
      FOREX: { provider: "Test", configured: false, message: "Not configured" },
    };
  if (path.includes("/markets/instruments") || path.endsWith("/watchlist"))
    return [];
  if (path.endsWith("/strategy/config"))
    return {
      version: 0,
      config: {
        enabled: false,
        min_confidence: 0.65,
        max_event_age_hours: 24,
        max_position_percent: 5,
        max_portfolio_exposure_percent: 50,
        cooldown_minutes: 60,
        daily_loss_limit_percent: 5,
      },
    };
  if (path.endsWith("/strategy/versions")) return [];
  if (path.endsWith("/ready")) return { status: "ready", database: "healthy" };
  return {};
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("application routes", () => {
  it("renders the workspace navigation with the current route active", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request) => ({
        ok: true,
        json: async () => apiResponse(String(request)),
      })),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const rendered = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/markets"]}>
          <Shell
            user={{ email: "visual-check@example.test" }}
            onLogout={vi.fn()}
          >
            <h1>Market watch</h1>
          </Shell>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Markets" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(screen.getByText("Paper environment")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();

    rendered.unmount();
    queryClient.clear();
  });

  it.each([
    ["/", "Dashboard"],
    ["/markets", "Market watch"],
    ["/news", "News terminal"],
    ["/paper", "Paper trading"],
    ["/strategy", "Strategy lab"],
    ["/backtest", "Historical backtesting"],
    ["/settings", "Settings & status"],
  ])("loads %s directly", async (path, title) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request) => ({
        ok: true,
        json: async () => apiResponse(String(request)),
      })),
    );
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const rendered = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
    rendered.unmount();
    queryClient.clear();
  });
});
