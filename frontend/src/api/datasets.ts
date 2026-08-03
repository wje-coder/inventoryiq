import { API_BASE_URL, apiFetch, getAccessToken, refreshAccessToken } from "./client";

export type DatasetStatus = "uploaded" | "validating" | "ready" | "failed" | "deleted";
export type DatasetFileType = "csv" | "xlsx";
export type ColumnDataType =
  | "string"
  | "integer"
  | "float"
  | "boolean"
  | "date"
  | "datetime"
  | "unknown";
export type FindingSeverity = "info" | "warning" | "error";
export type ValidationRunStatus = "running" | "passed" | "failed";

export type BusinessField =
  | "product_id"
  | "sku"
  | "upc"
  | "product_name"
  | "category"
  | "brand"
  | "supplier"
  | "unit_cost"
  | "retail_price"
  | "sale_price"
  | "quantity_available"
  | "quantity_sold"
  | "quantity_returned"
  | "order_id"
  | "order_date"
  | "return_date"
  | "customer_id"
  | "region"
  | "channel"
  | "status";

// Order matches app.models.dataset.BusinessField on the backend.
export const BUSINESS_FIELDS: BusinessField[] = [
  "product_id",
  "sku",
  "upc",
  "product_name",
  "category",
  "brand",
  "supplier",
  "unit_cost",
  "retail_price",
  "sale_price",
  "quantity_available",
  "quantity_sold",
  "quantity_returned",
  "order_id",
  "order_date",
  "return_date",
  "customer_id",
  "region",
  "channel",
  "status",
];

export const BUSINESS_FIELD_LABELS: Record<BusinessField, string> = {
  product_id: "Product ID",
  sku: "SKU",
  upc: "UPC",
  product_name: "Product name",
  category: "Category",
  brand: "Brand",
  supplier: "Supplier",
  unit_cost: "Unit cost",
  retail_price: "Retail price",
  sale_price: "Sale price",
  quantity_available: "Quantity available",
  quantity_sold: "Quantity sold",
  quantity_returned: "Quantity returned",
  order_id: "Order ID",
  order_date: "Order date",
  return_date: "Return date",
  customer_id: "Customer ID",
  region: "Region",
  channel: "Channel",
  status: "Status",
};

// Mirrors backend defaults (see backend/app/core/config.py). Only used to
// inform the user before upload; the backend is the source of truth and
// enforces its own limits regardless of what the client displays.
export const ACCEPTED_FILE_EXTENSIONS = [".csv", ".xlsx"];
export const MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024;

export interface Dataset {
  id: string;
  owner_user_id: string;
  display_name: string;
  original_filename: string;
  file_type: DatasetFileType;
  file_size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  status: DatasetStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DatasetColumn {
  id: string;
  source_name: string;
  normalized_name: string;
  position: number;
  inferred_type: ColumnDataType;
  nullable: boolean;
  sample_values: string[];
  mapped_business_field: BusinessField | null;
  created_at: string;
}

export interface DatasetColumnsResponse {
  columns: DatasetColumn[];
  available_analyses: string[];
}

export interface DatasetPreview {
  columns: string[];
  rows: Record<string, unknown>[];
  returned_row_count: number;
  total_row_count: number | null;
}

export interface ValidationFinding {
  severity: FindingSeverity;
  code: string;
  message: string;
  row_number: number | null;
  column_name: string | null;
}

export interface ValidationRun {
  id: string;
  status: ValidationRunStatus;
  row_count: number | null;
  column_count: number | null;
  summary: string | null;
  started_at: string;
  completed_at: string | null;
  findings: ValidationFinding[];
}

/**
 * Error raised by every function in this module. Dataset endpoints return
 * a structured `{code, message, findings}` error body (see
 * app/schemas/dataset.py DatasetErrorDetail) rather than a flat string,
 * so callers can show findings inline instead of just a generic message.
 */
export class DatasetApiError extends Error {
  status: number;
  code: string;
  findings: ValidationFinding[];

  constructor(status: number, code: string, message: string, findings: ValidationFinding[] = []) {
    super(message);
    this.name = "DatasetApiError";
    this.status = status;
    this.code = code;
    this.findings = findings;
  }
}

function datasetErrorFromBody(status: number, body: unknown): DatasetApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object") {
    const d = detail as { code?: string; message?: string; findings?: ValidationFinding[] };
    if (typeof d.message === "string") {
      return new DatasetApiError(
        status,
        d.code ?? "UNKNOWN_ERROR",
        d.message,
        Array.isArray(d.findings) ? d.findings : [],
      );
    }
  }
  if (typeof detail === "string") {
    return new DatasetApiError(status, "UNKNOWN_ERROR", detail);
  }
  return new DatasetApiError(status, "UNKNOWN_ERROR", `Request failed with status ${status}`);
}

async function datasetFetchJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, options);
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.clone().json();
    } catch {
      // response wasn't JSON; datasetErrorFromBody falls back to a generic message.
    }
    throw datasetErrorFromBody(response.status, body);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function listDatasets(): Promise<Dataset[]> {
  return datasetFetchJson<Dataset[]>("/datasets");
}

export async function getDataset(id: string): Promise<Dataset> {
  return datasetFetchJson<Dataset>(`/datasets/${id}`);
}

export async function getDatasetPreview(id: string): Promise<DatasetPreview> {
  return datasetFetchJson<DatasetPreview>(`/datasets/${id}/preview`);
}

export async function getDatasetColumns(id: string): Promise<DatasetColumnsResponse> {
  return datasetFetchJson<DatasetColumnsResponse>(`/datasets/${id}/columns`);
}

export async function updateDatasetDisplayName(id: string, displayName: string): Promise<Dataset> {
  return datasetFetchJson<Dataset>(`/datasets/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
}

export async function updateDatasetColumnMappings(
  id: string,
  columns: { column_id: string; mapped_business_field: BusinessField | null }[],
): Promise<DatasetColumnsResponse> {
  return datasetFetchJson<DatasetColumnsResponse>(`/datasets/${id}/columns`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ columns }),
  });
}

export async function deleteDataset(id: string): Promise<void> {
  await datasetFetchJson<void>(`/datasets/${id}`, { method: "DELETE" });
}

export async function revalidateDataset(id: string): Promise<Dataset> {
  return datasetFetchJson<Dataset>(`/datasets/${id}/validate`, { method: "POST" });
}

interface XhrResult {
  status: number;
  body: unknown;
}

function xhrUpload(
  file: File,
  displayName: string | undefined,
  token: string | null,
  onProgress: (percent: number) => void,
): Promise<XhrResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/datasets/upload`);
    xhr.withCredentials = true;
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      resolve({ status: xhr.status, body });
    };
    xhr.onerror = () => {
      reject(new DatasetApiError(0, "NETWORK_ERROR", "Network error during upload."));
    };
    xhr.onabort = () => {
      reject(new DatasetApiError(0, "UPLOAD_ABORTED", "Upload was cancelled."));
    };

    const formData = new FormData();
    formData.append("file", file);
    if (displayName) {
      formData.append("display_name", displayName);
    }
    xhr.send(formData);
  });
}

/**
 * Uploads a dataset file with progress reporting. Uses XMLHttpRequest
 * rather than fetch because fetch has no upload-progress event; mirrors
 * apiFetch's single silent-refresh-and-retry behavior on a 401 so an
 * expired access token doesn't fail an in-progress upload unnecessarily.
 */
export async function uploadDataset(
  file: File,
  displayName: string | undefined,
  onProgress: (percent: number) => void,
): Promise<Dataset> {
  let token = getAccessToken();
  let result = await xhrUpload(file, displayName, token, onProgress);

  if (result.status === 401) {
    token = await refreshAccessToken();
    if (token) {
      result = await xhrUpload(file, displayName, token, onProgress);
    }
  }

  if (result.status < 200 || result.status >= 300) {
    throw datasetErrorFromBody(result.status, result.body);
  }

  return result.body as Dataset;
}
