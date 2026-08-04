import type {
  AnalyticsSummary,
  AnomalyFinding,
  CategoriesResponse,
  DataQualityReport,
  KPIResult,
  ProductsResponse,
  RegionsResponse,
  SuppliersResponse,
  TrendsResponse,
} from "../api/analytics";
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

export function makeKPIResult(overrides: Partial<KPIResult> = {}): KPIResult {
  return {
    kpi_name: "revenue",
    value: 1000,
    unit: "USD",
    computed_at: new Date().toISOString(),
    ...overrides,
  };
}

export function makeAnalyticsSummary(overrides: Partial<AnalyticsSummary> = {}): AnalyticsSummary {
  return {
    snapshot: {
      id: "30000000-0000-0000-0000-000000000001",
      dataset_id: "10000000-0000-0000-0000-000000000001",
      job_id: "40000000-0000-0000-0000-000000000001",
      row_count: 5,
      column_count: 10,
      mapped_field_count: 8,
      summary: "15 KPI(s) computed; overall data quality 90.0/100.",
      created_at: new Date().toISOString(),
    },
    kpis: [makeKPIResult()],
    data_quality_overall_score: 90,
    channel_performance: [],
    ...overrides,
  };
}

export function makeDataQualityReport(
  overrides: Partial<DataQualityReport> = {},
): DataQualityReport {
  return {
    completeness_score: 95,
    validity_score: 90,
    consistency_score: 92,
    uniqueness_score: 100,
    overall_score: 94.25,
    created_at: new Date().toISOString(),
    findings: [],
    ...overrides,
  };
}

export function makeAnomalyFinding(overrides: Partial<AnomalyFinding> = {}): AnomalyFinding {
  return {
    anomaly_type: "Revenue spikes",
    severity: "warning",
    entity: "2024-06-01",
    metric: "revenue",
    value: 5000,
    z_score: 3.1,
    description: "Revenue spiked in 2024-06-01 (z-score 3.10).",
    ...overrides,
  };
}

export function makeTrendsResponse(overrides: Partial<TrendsResponse> = {}): TrendsResponse {
  return {
    dataset_id: "10000000-0000-0000-0000-000000000001",
    granularity: "monthly",
    points: [{ period: "2024-01-01", units_sold: 10, revenue: 100 }],
    ...overrides,
  };
}

export function makeProductsResponse(overrides: Partial<ProductsResponse> = {}): ProductsResponse {
  return {
    dataset_id: "10000000-0000-0000-0000-000000000001",
    top_products: [{ product_id: "P1", product_name: "Widget", units_sold: 10, revenue: 100 }],
    worst_products: [{ product_id: "P2", product_name: "Gadget", units_sold: 1, revenue: 10 }],
    ...overrides,
  };
}

export function makeCategoriesResponse(
  overrides: Partial<CategoriesResponse> = {},
): CategoriesResponse {
  return {
    dataset_id: "10000000-0000-0000-0000-000000000001",
    categories: [
      {
        dimension: "Tools",
        units_sold: 5,
        revenue: 50,
        gross_profit: 25,
        units_returned: 1,
        return_rate: 20,
      },
    ],
    top_brands: [],
    ...overrides,
  };
}

export function makeSuppliersResponse(
  overrides: Partial<SuppliersResponse> = {},
): SuppliersResponse {
  return {
    dataset_id: "10000000-0000-0000-0000-000000000001",
    suppliers: [
      {
        dimension: "Acme",
        units_sold: 5,
        revenue: 50,
        gross_profit: 25,
        units_returned: 1,
        return_rate: 20,
      },
    ],
    ...overrides,
  };
}

export function makeRegionsResponse(overrides: Partial<RegionsResponse> = {}): RegionsResponse {
  return {
    dataset_id: "10000000-0000-0000-0000-000000000001",
    regions: [
      {
        dimension: "East",
        units_sold: 5,
        revenue: 50,
        gross_profit: 25,
        units_returned: 1,
        return_rate: 20,
      },
    ],
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
