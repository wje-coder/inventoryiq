import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../context/AuthContext";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { createFetchMock, jsonResponse, makeFakeAccessToken, makeUser } from "../test/testUtils";
import { DatasetsPage } from "./DatasetsPage";

function renderDatasetsRoute() {
  return render(
    <MemoryRouter initialEntries={["/datasets"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<h1>Log in</h1>} />
          <Route
            path="/datasets"
            element={
              <ProtectedRoute>
                <DatasetsPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("DatasetsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("redirects an unauthenticated visitor to the login page", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ detail: "no session" }, 401),
        },
      ]),
    );

    renderDatasetsRoute();

    expect(await screen.findByRole("heading", { name: /log in/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^datasets$/i })).not.toBeInTheDocument();
  });

  it("shows the upload form and dataset list for an authenticated user", async () => {
    const accessToken = makeFakeAccessToken("viewer");
    const user = makeUser();

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ access_token: accessToken, token_type: "bearer" }),
        },
        {
          match: (url) => url.endsWith("/auth/me"),
          response: () => jsonResponse(user),
        },
        {
          match: (url) => url.endsWith("/datasets"),
          response: () => jsonResponse([]),
        },
      ]),
    );

    renderDatasetsRoute();

    expect(await screen.findByRole("heading", { name: /^datasets$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /upload a dataset/i })).toBeInTheDocument();
    expect(await screen.findByText(/no datasets uploaded yet/i)).toBeInTheDocument();
  });
});
