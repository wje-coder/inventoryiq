import { apiFetch } from "./client";

export type KPIName =
  | "revenue"
  | "gross_profit"
  | "gross_margin"
  | "average_selling_price"
  | "average_order_value"
  | "inventory_value"
  | "inventory_turnover"
  | "sell_through_rate"
  | "return_rate"
  | "return_cost"
  | "units_sold"
  | "units_returned"
  | "stockouts"
  | "overstock_count"
  | "low_inventory_count";

export const KPI_LABELS: Record<KPIName, string> = {
  revenue: "Revenue",
  gross_profit: "Gross Profit",
  gross_margin: "Gross Margin",
  average_selling_price: "Avg. Selling Price",
  average_order_value: "Avg. Order Value",
  inventory_value: "Inventory Value",
  inventory_turnover: "Inventory Turnover",
  sell_through_rate: "Sell-Through Rate",
  return_rate: "Return Rate",
  return_cost: "Return Cost",
  units_sold: "Units Sold",
  units_returned: "Units Returned",
  stockouts: "Stockouts",
  overstock_count: "Overstock Count",
  low_inventory_count: "Low Inventory Count",
};

export interface KPIResult {
  kpi_name: KPIName;
  value: number;
  unit: string;
  computed_at: string;
}

export interface DataQualityFinding {
  severity: "info" | "warning" | "error";
  category: string;
  description: string;
  recommendation: string;
  created_at: string;
}

export interface DataQualityReport {
  completeness_score: number;
  validity_score: number;
  consistency_score: number;
  uniqueness_score: number;
  overall_score: number;
  created_at: string;
  findings: DataQualityFinding[];
}

export interface AnalyticsJob {
  id: string;
  status: "running" | "completed" | "failed";
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface AnalyticsSnapshot {
  id: string;
  dataset_id: string;
  job_id: string;
  row_count: number;
  column_count: number;
  mapped_field_count: number;
  summary: string | null;
  created_at: string;
}

export interface ChannelPerformance {
  dimension: string;
  units_sold: number | null;
  revenue: number | null;
  gross_profit: number | null;
  units_returned: number | null;
  return_rate: number | null;
}

export interface AnalyticsSummary {
  snapshot: AnalyticsSnapshot;
  kpis: KPIResult[];
  data_quality_overall_score: number | null;
  channel_performance: ChannelPerformance[];
}

export interface KPIsResponse {
  snapshot: AnalyticsSnapshot;
  kpis: KPIResult[];
}

export interface RunAnalyticsResponse {
  job: AnalyticsJob;
  snapshot: AnalyticsSnapshot;
}

export interface AnomalyFinding {
  anomaly_type: string;
  severity: string;
  entity: string;
  metric: string;
  value: number;
  z_score: number;
  description: string;
}

export interface AnomaliesResponse {
  dataset_id: string;
  anomalies: AnomalyFinding[];
}

export interface TrendPoint {
  period: string;
  units_sold: number | null;
  revenue: number | null;
}

export interface TrendsResponse {
  dataset_id: string;
  granularity: "daily" | "weekly" | "monthly";
  points: TrendPoint[];
}

export interface ProductRanking {
  product_id: string;
  product_name: string | null;
  units_sold: number | null;
  revenue: number | null;
}

export interface ProductsResponse {
  dataset_id: string;
  top_products: ProductRanking[];
  worst_products: ProductRanking[];
}

export interface DimensionPerformance {
  dimension: string;
  units_sold: number | null;
  revenue: number | null;
  gross_profit: number | null;
  units_returned: number | null;
  return_rate: number | null;
}

export interface CategoriesResponse {
  dataset_id: string;
  categories: DimensionPerformance[];
  top_brands: DimensionPerformance[];
}

export interface SuppliersResponse {
  dataset_id: string;
  suppliers: DimensionPerformance[];
}

export interface RegionsResponse {
  dataset_id: string;
  regions: DimensionPerformance[];
}

export interface AnalyticsFilters {
  dateFrom?: string;
  dateTo?: string;
  category?: string;
  supplier?: string;
  region?: string;
  channel?: string;
}

/**
 * Error raised by every function in this module. Analytics endpoints
 * return a structured `{code, message}` error body (see
 * app/schemas/analytics.py AnalyticsErrorDetail).
 */
export class AnalyticsApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "AnalyticsApiError";
    this.status = status;
    this.code = code;
  }
}

function analyticsErrorFromBody(status: number, body: unknown): AnalyticsApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object") {
    const d = detail as { code?: string; message?: string };
    if (typeof d.message === "string") {
      return new AnalyticsApiError(status, d.code ?? "UNKNOWN_ERROR", d.message);
    }
  }
  if (typeof detail === "string") {
    return new AnalyticsApiError(status, "UNKNOWN_ERROR", detail);
  }
  return new AnalyticsApiError(status, "UNKNOWN_ERROR", `Request failed with status ${status}`);
}

function buildQuery(
  datasetId: string,
  filters: AnalyticsFilters = {},
  extra: Record<string, string | number | undefined> = {},
): string {
  const params = new URLSearchParams();
  params.set("dataset_id", datasetId);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.category) params.set("category", filters.category);
  if (filters.supplier) params.set("supplier", filters.supplier);
  if (filters.region) params.set("region", filters.region);
  if (filters.channel) params.set("channel", filters.channel);
  for (const [key, value] of Object.entries(extra)) {
    if (value !== undefined) params.set(key, String(value));
  }
  return params.toString();
}

async function analyticsFetchJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.clone().json();
    } catch {
      // response wasn't JSON; analyticsErrorFromBody falls back to a generic message.
    }
    throw analyticsErrorFromBody(response.status, body);
  }
  return (await response.json()) as T;
}

export async function runAnalytics(datasetId: string): Promise<RunAnalyticsResponse> {
  const response = await apiFetch(`/analytics/run?dataset_id=${encodeURIComponent(datasetId)}`, {
    method: "POST",
  });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.clone().json();
    } catch {
      // response wasn't JSON; analyticsErrorFromBody falls back to a generic message.
    }
    throw analyticsErrorFromBody(response.status, body);
  }
  return (await response.json()) as RunAnalyticsResponse;
}

export async function getAnalyticsSummary(datasetId: string): Promise<AnalyticsSummary> {
  return analyticsFetchJson<AnalyticsSummary>(`/analytics/summary?${buildQuery(datasetId)}`);
}

export async function getKPIs(datasetId: string): Promise<KPIsResponse> {
  return analyticsFetchJson<KPIsResponse>(`/analytics/kpis?${buildQuery(datasetId)}`);
}

export async function getDataQuality(datasetId: string): Promise<DataQualityReport> {
  return analyticsFetchJson<DataQualityReport>(`/analytics/data-quality?${buildQuery(datasetId)}`);
}

export async function getAnomalies(
  datasetId: string,
  filters: AnalyticsFilters = {},
): Promise<AnomaliesResponse> {
  return analyticsFetchJson<AnomaliesResponse>(
    `/analytics/anomalies?${buildQuery(datasetId, filters)}`,
  );
}

export async function getTrends(
  datasetId: string,
  granularity: "daily" | "weekly" | "monthly" = "monthly",
  filters: AnalyticsFilters = {},
): Promise<TrendsResponse> {
  const query = buildQuery(datasetId, filters, { granularity });
  return analyticsFetchJson<TrendsResponse>(`/analytics/trends?${query}`);
}

export async function getProducts(
  datasetId: string,
  filters: AnalyticsFilters = {},
  limit?: number,
): Promise<ProductsResponse> {
  const query = buildQuery(datasetId, filters, { limit });
  return analyticsFetchJson<ProductsResponse>(`/analytics/products?${query}`);
}

export async function getCategories(
  datasetId: string,
  filters: AnalyticsFilters = {},
  limit?: number,
): Promise<CategoriesResponse> {
  const query = buildQuery(datasetId, filters, { limit });
  return analyticsFetchJson<CategoriesResponse>(`/analytics/categories?${query}`);
}

export async function getSuppliers(
  datasetId: string,
  filters: AnalyticsFilters = {},
  limit?: number,
): Promise<SuppliersResponse> {
  const query = buildQuery(datasetId, filters, { limit });
  return analyticsFetchJson<SuppliersResponse>(`/analytics/suppliers?${query}`);
}

export async function getRegions(
  datasetId: string,
  filters: AnalyticsFilters = {},
  limit?: number,
): Promise<RegionsResponse> {
  const query = buildQuery(datasetId, filters, { limit });
  return analyticsFetchJson<RegionsResponse>(`/analytics/regions?${query}`);
}
