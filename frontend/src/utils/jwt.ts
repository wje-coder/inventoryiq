/**
 * Minimal, dependency-free JWT payload decoder.
 *
 * This does NOT verify the token's signature — it is only used client-side
 * to read the `exp` claim for scheduling a proactive refresh. The backend
 * is the sole source of truth for whether a token is actually valid.
 */
export interface JwtPayload {
  sub: string;
  role: string;
  type: string;
  iat: number;
  exp: number;
  [key: string]: unknown;
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;

  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const json = decodeURIComponent(
      atob(padded)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join(""),
    );
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function getExpiryMs(token: string): number | null {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return null;
  return payload.exp * 1000;
}
