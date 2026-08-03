import { useEffect, useState } from "react";

import { API_BASE_URL } from "../api/client";
import { NavBar } from "../components/NavBar";
import { useAuth } from "../context/AuthContext";

interface HealthResponse {
  status: string;
  database: string;
}

type HealthState =
  | { kind: "loading" }
  | { kind: "success"; data: HealthResponse }
  | { kind: "error"; message: string };

export function DashboardPage() {
  const { user } = useAuth();
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function fetchHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
        const data = (await response.json()) as HealthResponse;
        setHealth({ kind: "success", data });
      } catch (error) {
        if (controller.signal.aborted) return;
        setHealth({
          kind: "error",
          message: error instanceof Error ? error.message : "Unknown error",
        });
      }
    }

    void fetchHealth();
    return () => controller.abort();
  }, []);

  return (
    <>
      <NavBar />
      <main className="status-card">
        <h1>InventoryIQ</h1>
        {user && (
          <p data-testid="profile">
            Signed in as {user.full_name} ({user.email}) · role: {user.role}
          </p>
        )}

        {health.kind === "loading" && <p>Checking backend health…</p>}
        {health.kind === "success" && (
          <p className="status-ok" data-testid="health-status">
            Backend status: {health.data.status} · Database: {health.data.database}
          </p>
        )}
        {health.kind === "error" && (
          <p className="status-error" data-testid="health-status">
            Unable to reach backend: {health.message}
          </p>
        )}
      </main>
    </>
  );
}
