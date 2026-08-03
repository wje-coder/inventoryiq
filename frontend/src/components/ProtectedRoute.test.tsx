import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../context/AuthContext";
import { ProtectedRoute } from "./ProtectedRoute";
import { createFetchMock, jsonResponse, makeFakeAccessToken, makeUser } from "../test/testUtils";

describe("ProtectedRoute", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("redirects to /login when there is no session", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ detail: "no session" }, 401),
        },
      ]),
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <ProtectedRoute>
            <p>Secret content</p>
          </ProtectedRoute>
        </AuthProvider>
      </MemoryRouter>,
    );

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
  });

  it("denies access when the user's role is not in allowedRoles", async () => {
    const accessToken = makeFakeAccessToken("viewer");
    const viewer = makeUser({ role: "viewer" });

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ access_token: accessToken, token_type: "bearer" }),
        },
        {
          match: (url) => url.endsWith("/auth/me"),
          response: () => jsonResponse(viewer),
        },
      ]),
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <ProtectedRoute allowedRoles={["admin"]}>
            <p>Secret content</p>
          </ProtectedRoute>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();
    expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
  });

  it("renders children when the user has an allowed role", async () => {
    const accessToken = makeFakeAccessToken("admin");
    const admin = makeUser({ role: "admin" });

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ access_token: accessToken, token_type: "bearer" }),
        },
        {
          match: (url) => url.endsWith("/auth/me"),
          response: () => jsonResponse(admin),
        },
      ]),
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <ProtectedRoute allowedRoles={["admin"]}>
            <p>Secret content</p>
          </ProtectedRoute>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Secret content")).toBeInTheDocument();
  });
});
