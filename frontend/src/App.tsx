import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./context/AuthContext";
import "./index.css";
import { AnalyticsDashboardPage } from "./pages/AnalyticsDashboardPage";
import { AnomaliesPage } from "./pages/AnomaliesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DataQualityPage } from "./pages/DataQualityPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/datasets"
            element={
              <ProtectedRoute>
                <DatasetsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics"
            element={
              <ProtectedRoute>
                <AnalyticsDashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics/data-quality"
            element={
              <ProtectedRoute>
                <DataQualityPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics/anomalies"
            element={
              <ProtectedRoute>
                <AnomaliesPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
