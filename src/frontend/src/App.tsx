import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { AlertsPage } from "./pages/AlertsPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ScannerPage } from "./pages/ScannerPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WatchlistsPage } from "./pages/WatchlistsPage";

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="/watchlists" element={<WatchlistsPage />} />
        <Route path="/scanner" element={<ScannerPage />} />
        <Route path="/analysis/:symbol" element={<AnalysisPage />} />
        <Route path="/analysis/:symbol/*" element={<AnalysisPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
