import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { ProtectedRoute } from "../components/ProtectedRoute";
import {
  createFetchMock,
  jsonResponse,
  makeDataQualityReport,
  makeDataset,
  makeFakeAccessToken,
  makeUser,
} from "../test/testUtils";
import { DataQualityPage } from "./DataQualityPage";

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={["/analytics/data-quality"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<h1>Log in</h1>} />
          <Route
            path="/analytics/data-quality"
            element={
              <ProtectedRoute>
                <DataQualityPage />
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

describe("DataQualityPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a prompt when analytics have not been run yet", async () => {
    const dataset = makeDataset({ id: "1" });
    stubAuthedFetch([
      { match: (url) => url.endsWith("/datasets"), response: () => jsonResponse([dataset]) },
      {
        match: (url) => url.includes("/analytics/data-quality"),
        response: () =>
          jsonResponse({ detail: { code: "ANALYTICS_NOT_RUN", message: "not run yet" } }, 404),
      },
    ]);

    renderRoute();

    expect(
      await screen.findByText(/run analytics from the dashboard page first/i),
    ).toBeInTheDocument();
  });

  it("renders the four component scores, overall score, and findings table", async () => {
    const dataset = makeDataset({ id: "1" });
    const report = makeDataQualityReport({
      overall_score: 88.5,
      findings: [
        {
          severity: "warning",
          category: "Missing values",
          description: "Missing values found in: category (2).",
          recommendation: "Fill in missing values.",
          created_at: new Date().toISOString(),
        },
      ],
    });

    stubAuthedFetch([
      { match: (url) => url.endsWith("/datasets"), response: () => jsonResponse([dataset]) },
      {
        match: (url) => url.includes("/analytics/data-quality"),
        response: () => jsonResponse(report),
      },
    ]);

    renderRoute();

    expect(await screen.findByText("88.5")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Data quality findings" })).toBeInTheDocument();
    expect(screen.getByText("Missing values")).toBeInTheDocument();
    expect(screen.getByText("Fill in missing values.")).toBeInTheDocument();
  });
});
