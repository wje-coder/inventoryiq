import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { createFetchMock, jsonResponse, makeFakeAccessToken, makeUser } from "./test/testUtils";

describe("App", () => {
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

    render(<App />);

    expect(await screen.findByRole("heading", { name: /log in/i })).toBeInTheDocument();
  });

  it("lets a user log in and reach the protected dashboard", async () => {
    const user = userEvent.setup();
    const accessToken = makeFakeAccessToken("viewer");
    const loggedInUser = makeUser({ email: "jane@example.com", full_name: "Jane Doe" });

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ detail: "no session" }, 401),
        },
        {
          match: (url, init) => url.endsWith("/auth/login") && init?.method === "POST",
          response: () =>
            jsonResponse({ access_token: accessToken, token_type: "bearer", user: loggedInUser }),
        },
        {
          match: (url) => url.endsWith("/health"),
          response: () => jsonResponse({ status: "ok", database: "ok" }),
        },
      ]),
    );

    render(<App />);

    await screen.findByRole("heading", { name: /log in/i });

    await user.type(screen.getByLabelText(/email/i), "jane@example.com");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByTestId("profile")).toHaveTextContent(
      "Signed in as Jane Doe (jane@example.com) · role: viewer",
    );

    await waitFor(() => {
      expect(screen.getByTestId("health-status")).toHaveTextContent(
        "Backend status: ok · Database: ok",
      );
    });
  });

  it("shows an error and stays on the login page when credentials are rejected", async () => {
    const user = userEvent.setup();

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/auth/refresh"),
          response: () => jsonResponse({ detail: "no session" }, 401),
        },
        {
          match: (url, init) => url.endsWith("/auth/login") && init?.method === "POST",
          response: () => jsonResponse({ detail: "Incorrect email or password." }, 401),
        },
      ]),
    );

    render(<App />);

    await screen.findByRole("heading", { name: /log in/i });
    await user.type(screen.getByLabelText(/email/i), "jane@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong-password");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect email or password/i);
  });
});
