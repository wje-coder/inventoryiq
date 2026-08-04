import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { ProtectedRoute } from "../components/ProtectedRoute";
import {
  createFetchMock,
  jsonResponse,
  makeAnomalyFinding,
  makeDataset,
  makeFakeAccessToken,
  makeUser,
} from "../test/testUtils";
import { AnomaliesPage } from "./AnomaliesPage";

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={["/analytics/anomalies"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<h1>Log in</h1>} />
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
    </MemoryRouter>,
  );
}

function stubAuthedFetch(extraRoutes: Parameters<typeof createFetchMock>[0]) {
  const accessToken = makeFakeAccessToken("viewer");
  const user = makeUser();
  vi.stubGlobal(
    "fetch",
    createFetchMock([
      {
        match: (url) => url.endsWith("/auth/refresh"),
        response: () => jsonResponse({ access_token: accessToken, token_type: "bearer" }),
      },
      { match: (url) => url.endsWith("/auth/me"), response: () => jsonResponse(user) },
      ...extraRoutes,
    ]),
  );
}

describe("AnomaliesPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows an empty state when no anomalies are detected", async () => {
    const dataset = makeDataset({ id: "1" });
    stubAuthedFetch([
      { match: (url) => url.endsWith("/datasets"), response: () => jsonResponse([dataset]) },
      {
        match: (url) => url.includes("/analytics/anomalies"),
        response: () => jsonResponse({ dataset_id: "1", anomalies: [] }),
      },
    ]);

    renderRoute();

    expect(await screen.findByText(/no anomalies detected/i)).toBeInTheDocument();
  });

  it("renders a row per detected anomaly", async () => {
    const dataset = makeDataset({ id: "1" });
    const anomaly = makeAnomalyFinding({ anomaly_type: "Revenue spikes", entity: "2024-06-01" });

    stubAuthedFetch([
      { match: (url) => url.endsWith("/datasets"), response: () => jsonResponse([dataset]) },
      {
        match: (url) => url.includes("/analytics/anomalies"),
        response: () => jsonResponse({ dataset_id: "1", anomalies: [anomaly] }),
      },
    ]);

    renderRoute();

    expect(await screen.findByRole("table", { name: "Detected anomalies" })).toBeInTheDocument();
    expect(screen.getByText("Revenue spikes")).toBeInTheDocument();
    expect(screen.getByText("2024-06-01")).toBeInTheDocument();
  });
});
