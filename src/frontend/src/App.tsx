import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { AlertsPage } from "./pages/AlertsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { LoginPage } from "./pages/LoginPage";
import { DiscoverPage } from "./pages/DiscoverPage";
import { NewsHubPage } from "./pages/NewsHubPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PaperTradingPage } from "./pages/PaperTradingPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { ScannerPage } from "./pages/ScannerPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WatchlistsPage } from "./pages/WatchlistsPage";

// AnalysisPage pulls in the heavy lightweight-charts bundle; lazy so the
// initial Login/Dashboard route stays fast.
const AnalysisPage = lazy(() =>
  import("./pages/AnalysisPage").then((m) => ({ default: m.AnalysisPage })),
);
const AdminPage = lazy(() =>
  import("./pages/AdminPage").then((m) => ({ default: m.AdminPage })),
);
// DocsPage pulls in react-markdown + remark-gfm — lazy so the docs
// dependency stack only loads when the user actually opens help.
const DocsPage = lazy(() =>
  import("./pages/DocsPage").then((m) => ({ default: m.DocsPage })),
);

function ChartFallback() {
  return (
    <div className="flex h-64 items-center justify-center text-sm text-slate-400">
      Loading chart…
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/watchlists" element={<WatchlistsPage />} />
        <Route path="/scanner" element={<ScannerPage />} />
        <Route
          path="/analysis/:symbol"
          element={
            <Suspense fallback={<ChartFallback />}>
              <AnalysisPage />
            </Suspense>
          }
        />
        <Route
          path="/analysis/:symbol/*"
          element={
            <Suspense fallback={<ChartFallback />}>
              <AnalysisPage />
            </Suspense>
          }
        />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/news" element={<NewsHubPage />} />
        <Route path="/discover" element={<DiscoverPage />} />
        <Route path="/paper-trading" element={<PaperTradingPage />} />
        <Route
          path="/docs"
          element={
            <Suspense fallback={<ChartFallback />}>
              <DocsPage />
            </Suspense>
          }
        />
        <Route
          path="/docs/:slug"
          element={
            <Suspense fallback={<ChartFallback />}>
              <DocsPage />
            </Suspense>
          }
        />
        <Route path="/settings" element={<SettingsPage />} />
        <Route
          path="/admin"
          element={
            <Suspense fallback={<ChartFallback />}>
              <AdminPage />
            </Suspense>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
