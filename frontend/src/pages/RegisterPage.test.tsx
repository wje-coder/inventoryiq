import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../context/AuthContext";
import { RegisterPage } from "./RegisterPage";
import { createFetchMock, jsonResponse, makeFakeAccessToken, makeUser } from "../test/testUtils";

function renderRegisterPage() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("RegisterPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a validation error for a short password without calling the API", async () => {
    const user = userEvent.setup();
    const fetchMock = createFetchMock([
      {
        match: (url) => url.endsWith("/auth/refresh"),
        response: () => jsonResponse({ detail: "no session" }, 401),
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderRegisterPage();
    await screen.findByRole("heading", { name: /register/i });

    await user.type(screen.getByLabelText(/full name/i), "Jane Doe");
    await user.type(screen.getByLabelText(/email/i), "jane@example.com");
    await user.type(screen.getByLabelText(/password/i), "short");
    await user.click(screen.getByRole("button", { name: /register/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 8 characters/i);
    // Only the initial silent-refresh call should have happened - never /auth/register.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("registers successfully with a valid form", async () => {
    const user = userEvent.setup();
    const accessToken = makeFakeAccessToken("admin");
    const newUser = makeUser({ email: "jane@example.com", full_name: "Jane Doe", role: "admin" });

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ detail: "no session" }, 401),
        },
        {
          match: (url, init) => url.endsWith("/auth/register") && init?.method === "POST",
          response: () =>
            jsonResponse(
              { access_token: accessToken, token_type: "bearer", user: newUser },
              201,
            ),
        },
      ]),
    );

    renderRegisterPage();
    await screen.findByRole("heading", { name: /register/i });

    await user.type(screen.getByLabelText(/full name/i), "Jane Doe");
    await user.type(screen.getByLabelText(/email/i), "jane@example.com");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });
});
