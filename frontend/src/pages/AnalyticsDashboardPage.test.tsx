import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { ProtectedRoute } from "../components/ProtectedRoute";
import {
  createFetchMock,
  jsonResponse,
  makeAnalyticsSummary,
  makeCategoriesResponse,
  makeDataset,
  makeFakeAccessToken,
  makeProductsResponse,
  makeRegionsResponse,
  makeSuppliersResponse,
  makeTrendsResponse,
  makeUser,
} from "../test/testUtils";
import { AnalyticsDashboardPage } from "./AnalyticsDashboardPage";

function renderAnalyticsRoute() {
  return render(
    <MemoryRouter initialEntries={["/analytics"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<h1>Log in</h1>} />
          <Route
            path="/analytics"
            element={
              <ProtectedRoute>
                <AnalyticsDashboardPage />
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

describe("AnalyticsDashboardPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a message when there are no ready datasets", async () => {
    stubAuthedFetch([
      { match: (url) => url.endsWith("/datasets"), response: () => jsonResponse([]) },
    ]);

    renderAnalyticsRoute();

    expect(await screen.findByText(/no ready datasets available/i)).toBeInTheDocument();
  });

  it("prompts to run analytics when none have been computed yet", async () => {
    const dataset = makeDataset({ id: "1" });
    stubAuthedFetch([
      { match: (url) => url.endsWith("/datasets"), response: () => jsonResponse([dataset]) },
      {
        match: (url) => url.includes("/analytics/trends"),
        response: () => jsonResponse(makeTrendsResponse()),
      },
      {
        match: (url) => url.includes("/analytics/products"),
        response: () => jsonResponse(makeProductsResponse()),
      },
      {
        match: (url) => url.includes("/analytics/categories"),
        response: () => jsonResponse(makeCategoriesResponse()),
      },
      {
        match: (url) => url.includes("/analytics/suppliers"),
        response: () => jsonResponse(makeSuppliersResponse()),
      },
      {
        match: (url) => url.includes("/analytics/regions"),
        response: () => jsonResponse(makeRegionsResponse()),
      },
      {
        match: (url) => url.includes("/analytics/summary"),
        response: () =>
          jsonResponse({ detail: { code: "ANALYTICS_NOT_RUN", message: "not run yet" } }, 404),
      },
    ]);

    renderAnalyticsRoute();

    expect(await screen.findByRole("button", { name: /run analytics/i })).toBeInTheDocument();
  });

  it("renders KPI cards, charts, and product rankings once analytics have run", async () => {
    const dataset = makeDataset({ id: "1" });
    stubAuthedFetch([
      { match: (url) => url.endsWith("/datasets"), response: () => jsonResponse([dataset]) },
      {
        match: (url) => url.includes("/analytics/trends"),
        response: () => jsonResponse(makeTrendsResponse()),
      },
      {
        match: (url) => url.includes("/analytics/products"),
        response: () => jsonResponse(makeProductsResponse()),
      },
      {
        match: (url) => url.includes("/analytics/categories"),
        response: () => jsonResponse(makeCategoriesResponse()),
      },
      {
        match: (url) => url.includes("/analytics/suppliers"),
        response: () => jsonResponse(makeSuppliersResponse()),
      },
      {
        match: (url) => url.includes("/analytics/regions"),
        response: () => jsonResponse(makeRegionsResponse()),
      },
      {
        match: (url) => url.includes("/analytics/summary"),
        response: () => jsonResponse(makeAnalyticsSummary()),
      },
    ]);

    renderAnalyticsRoute();

    expect(await screen.findByText("Executive KPIs")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Revenue" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Monthly Revenue Trend" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Top Selling Products" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Worst Selling Products" })).toBeInTheDocument();
  });
});
