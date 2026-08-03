/**
 * Low-level fetch wrapper shared by every API call.
 *
 * The access token is kept in module-level memory only (never
 * localStorage/sessionStorage) so it cannot be read by a malicious script
 * via storage APIs. The refresh token lives exclusively in an httpOnly
 * cookie set by the backend, which JS can neither read nor tamper with;
 * `credentials: "include"` is required on every request so that cookie is
 * sent to (and can be set by) the API.
 */

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const data = (await response.clone().json()) as { detail?: string };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    // response wasn't JSON; fall through to the generic message.
  }
  return `Request failed with status ${response.status}`;
}

/**
 * Calls POST /auth/refresh using the httpOnly cookie. On success, updates
 * the in-memory access token and returns it; on failure, clears it and
 * returns null. Never throws.
 */
export async function refreshAccessToken(): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setAccessToken(null);
      return null;
    }
    const data = (await response.json()) as { access_token: string };
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    setAccessToken(null);
    return null;
  }
}

interface ApiFetchOptions extends RequestInit {
  /** Attach the Authorization header and attempt a silent refresh on 401. Default true. */
  auth?: boolean;
}

/**
 * Fetch wrapper that attaches the bearer token, and on a 401 makes a
 * single attempt to silently refresh the access token (via the refresh
 * cookie) and retry the original request once before giving up.
 */
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  const { auth = true, headers, ...rest } = options;

  const buildHeaders = (): HeadersInit => {
    const combined = new Headers(headers);
    if (auth && accessToken) {
      combined.set("Authorization", `Bearer ${accessToken}`);
    }
    return combined;
  };

  let response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: buildHeaders(),
    credentials: "include",
  });

  if (response.status === 401 && auth) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(`${API_BASE_URL}${path}`, {
        ...rest,
        headers: buildHeaders(),
        credentials: "include",
      });
    }
  }

  return response;
}

export async function apiFetchJson<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const response = await apiFetch(path, options);
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response), response.status, null);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
