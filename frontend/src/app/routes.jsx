import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { PageLoading } from "../components/feedback/PageLoading";
import { PageTitle } from "../components/ui/PageTitle";
const DashboardPage = lazy(() =>
  import("../features/dashboard/DashboardPage.jsx").then((m) => ({
    default: m.DashboardPage,
  })),
);
const NewsPage = lazy(() =>
  import("../features/news/NewsPage.jsx").then((m) => ({
    default: m.NewsPage,
  })),
);
const MarketsPage = lazy(() =>
  import("../features/markets/MarketsPage.jsx").then((m) => ({
    default: m.MarketsPage,
  })),
);
const PaperPage = lazy(() =>
  import("../features/paper-trading/PaperPage.jsx").then((m) => ({
    default: m.PaperPage,
  })),
);
const StrategyPage = lazy(
  () => import("../features/strategies/StrategyPage.jsx"),
);
const BacktestPage = lazy(
  () => import("../features/backtesting/BacktestPage.jsx"),
);
const SettingsPage = lazy(
  () => import("../features/settings/SettingsPage.jsx"),
);
function NotFoundPage() {
  return (
    <PageTitle
      eyebrow="NOT FOUND"
      title="Page not found"
      subtitle="The address may have changed or may not be part of this workspace."
    />
  );
}
export function AppRoutes() {
  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/markets" element={<MarketsPage />} />
        <Route path="/paper" element={<PaperPage />} />
        <Route path="/strategy" element={<StrategyPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
