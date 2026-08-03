import type { Role, User } from "../api/auth";
import type { Dataset, DatasetColumn } from "../api/datasets";

/** Builds a structurally-valid (unsigned) JWT for tests. The app never
 * verifies the signature client-side - it only reads `exp` to schedule a
 * proactive refresh - so a fake signature is fine here. */
export function makeFakeAccessToken(role: Role = "viewer", expiresInSeconds = 3600): string {
  const header = { alg: "none", typ: "JWT" };
  const payload = {
    sub: "00000000-0000-0000-0000-000000000000",
    role,
    type: "access",
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + expiresInSeconds,
  };
  const encode = (obj: unknown) => btoa(JSON.stringify(obj)).replace(/=+$/, "");
  return `${encode(header)}.${encode(payload)}.fake-signature`;
}

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "00000000-0000-0000-0000-000000000000",
    email: "user@example.com",
    full_name: "Test User",
    role: "viewer",
    is_active: true,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

interface MockRoute {
  match: (url: string, init?: RequestInit) => boolean;
  response: (url: string, init?: RequestInit) => Promise<Response> | Response;
}

/** A tiny fetch router: registers URL/method-matched handlers so each test
 * only has to describe the endpoints it actually cares about. */
export function createFetchMock(routes: MockRoute[]): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const route = routes.find((r) => r.match(url, init));
    if (!route) {
      throw new Error(`Unhandled fetch: ${init?.method ?? "GET"} ${url}`);
    }
    return route.response(url, init);
  }) as unknown as typeof fetch;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Structured error body shaped like app.schemas.dataset.DatasetErrorDetail,
 * as returned by every dataset endpoint's HTTPException(detail=...). */
export function datasetErrorResponse(
  code: string,
  message: string,
  status = 400,
  findings: unknown[] = [],
): Response {
  return jsonResponse({ detail: { code, message, findings } }, status);
}

export function makeDataset(overrides: Partial<Dataset> = {}): Dataset {
  return {
    id: "10000000-0000-0000-0000-000000000001",
    owner_user_id: "00000000-0000-0000-0000-000000000000",
    display_name: "Q1 Sales",
    original_filename: "q1_sales.csv",
    file_type: "csv",
    file_size_bytes: 2048,
    row_count: 100,
    column_count: 4,
    status: "ready",
    error_message: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

export function makeDatasetColumn(overrides: Partial<DatasetColumn> = {}): DatasetColumn {
  return {
    id: "20000000-0000-0000-0000-000000000001",
    source_name: "product_id",
    normalized_name: "product_id",
    position: 0,
    inferred_type: "string",
    nullable: false,
    sample_values: ["P001", "P002"],
    mapped_business_field: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

interface XhrMockResult {
  status: number;
  body: unknown;
}

interface XhrMockOptions {
  /** Percent values emitted via upload.onprogress before the final response. */
  progressSteps?: number[];
  /** Simulate a network-level failure (xhr.onerror) instead of a response. */
  networkError?: boolean;
}

/**
 * Installs a fake XMLHttpRequest (jsdom's is not a real network client and
 * vitest has no built-in XHR mock). Used for api/datasets.ts#uploadDataset,
 * which uses XHR instead of fetch specifically to get upload progress
 * events. Returns the list of requests made, each with its recorded
 * Authorization header, so 401-retry behavior can be asserted too.
 */
export function installXhrMock(
  respond: (requestCount: number) => XhrMockResult,
  options: XhrMockOptions = {},
): { requests: { authHeader: string | null }[] } {
  const requests: { authHeader: string | null }[] = [];

  class FakeXHR {
    status = 0;
    responseText = "";
    withCredentials = false;
    upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onabort: (() => void) | null = null;
    private headers: Record<string, string> = {};

    open(_method: string, _url: string) {
      // no-op: URL/method aren't asserted on here.
    }

    setRequestHeader(name: string, value: string) {
      this.headers[name] = value;
    }

    send(_body?: unknown) {
      requests.push({ authHeader: this.headers["Authorization"] ?? null });
      const requestCount = requests.length;

      // Emit each progress step - and the final response - on its own
      // macrotask (setTimeout) rather than all synchronously in one
      // microtask. A real upload has an observable "in progress" period;
      // batching everything into a single tick would let React coalesce
      // the "uploading" and "success"/"error" state updates into one
      // render, so a test asserting on the intermediate progress UI would
      // never see it. Spacing steps out mirrors real timing closely
      // enough for that intermediate render to actually commit.
      const steps = options.progressSteps ?? [100];
      let stepIndex = 0;

      const emitNext = () => {
        if (stepIndex < steps.length) {
          const percent = steps[stepIndex];
          stepIndex += 1;
          this.upload.onprogress?.({
            lengthComputable: true,
            loaded: percent,
            total: 100,
          } as ProgressEvent);
          setTimeout(emitNext, 0);
          return;
        }

        if (options.networkError) {
          this.onerror?.();
          return;
        }

        const result = respond(requestCount);
        this.status = result.status;
        this.responseText = JSON.stringify(result.body);
        this.onload?.();
      };

      setTimeout(emitNext, 0);
    }
  }

  vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);
  return { requests };
}
