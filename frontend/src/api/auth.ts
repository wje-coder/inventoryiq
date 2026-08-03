import { apiFetchJson, refreshAccessToken, setAccessToken } from "./client";

export type Role = "admin" | "analyst" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export async function register(
  email: string,
  password: string,
  fullName: string,
): Promise<AuthResponse> {
  const data = await apiFetchJson<AuthResponse>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName }),
    auth: false,
  });
  setAccessToken(data.access_token);
  return data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);

  const data = await apiFetchJson<AuthResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
    auth: false,
  });
  setAccessToken(data.access_token);
  return data;
}

export async function logout(): Promise<void> {
  try {
    await apiFetchJson<void>("/auth/logout", { method: "POST" });
  } finally {
    setAccessToken(null);
  }
}

export async function fetchMe(): Promise<User> {
  return apiFetchJson<User>("/auth/me");
}

/**
 * Attempts to restore a session on app load using the httpOnly refresh
 * cookie. Returns the current user on success, or null if there was no
 * valid session (e.g. first visit, or the refresh token expired/was
 * revoked by logout).
 */
export async function restoreSession(): Promise<User | null> {
  const token = await refreshAccessToken();
  if (!token) return null;

  try {
    return await fetchMe();
  } catch {
    setAccessToken(null);
    return null;
  }
}
