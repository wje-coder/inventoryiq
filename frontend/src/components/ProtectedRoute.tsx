import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import type { Role } from "../api/auth";

interface ProtectedRouteProps {
  children: ReactNode;
  /** If provided, the current user's role must be one of these. */
  allowedRoles?: Role[];
}

export function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <p>Loading…</p>;
  }

  if (status === "unauthenticated" || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <main className="status-card">
        <h1>Access denied</h1>
        <p className="status-error">Your role ({user.role}) cannot view this page.</p>
      </main>
    );
  }

  return <>{children}</>;
}
