import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { AlertsPage } from "./pages/AlertsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
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
