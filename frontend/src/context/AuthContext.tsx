import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import * as authApi from "../api/auth";
import type { User } from "../api/auth";
import { getExpiryMs } from "../utils/jwt";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// Refresh a little before actual expiry so a request never races an
// about-to-expire token.
const REFRESH_SKEW_MS = 30_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRefresh = useCallback((accessToken: string) => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);

    const expiryMs = getExpiryMs(accessToken);
    if (!expiryMs) return;

    const delay = Math.max(expiryMs - Date.now() - REFRESH_SKEW_MS, 0);
    refreshTimer.current = setTimeout(async () => {
      const restoredUser = await authApi.restoreSession();
      if (restoredUser) {
        setUser(restoredUser);
        setStatus("authenticated");
      } else {
        setUser(null);
        setStatus("unauthenticated");
      }
    }, delay);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const restoredUser = await authApi.restoreSession();
      if (cancelled) return;

      if (restoredUser) {
        setUser(restoredUser);
        setStatus("authenticated");
      } else {
        setUser(null);
        setStatus("unauthenticated");
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    try {
      const response = await authApi.login(email, password);
      setUser(response.user);
      setStatus("authenticated");
      scheduleRefresh(response.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
      throw err;
    }
  }, [scheduleRefresh]);

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      setError(null);
      try {
        const response = await authApi.register(email, password, fullName);
        setUser(response.user);
        setStatus("authenticated");
        scheduleRefresh(response.access_token);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Registration failed.");
        throw err;
      }
    },
    [scheduleRefresh],
  );

  const logout = useCallback(async () => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    await authApi.logout();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, error, login, register, logout }),
    [status, user, error, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
