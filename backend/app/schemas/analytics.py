"""Pydantic schemas for the Phase 4 analytics API.

Two response families, matching the persisted-vs-live split described in
app/models/analytics.py and app/services/kpi_engine.py:

- Snapshot-backed reads (AnalyticsSummaryResponse, KPIsResponse,
  DataQualityReportRead) describe the most recent POST /analytics/run
  and never take filter query params - they're a frozen point-in-time
  read.
- Live-computed reads (AnomalyFindingRead, TrendPointRead,
  ProductRankingRead, DimensionPerformanceRead) are recomputed from the
  dataset's normalized rows on every call and do take filter params.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.analytics import AnalyticsJobStatus, KPIName
from app.models.dataset import FindingSeverity


class KPIResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kpi_name: KPIName
    value: float
    unit: str
    computed_at: datetime


class DataQualityFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity: FindingSeverity
    category: str
    description: str
    recommendation: str
    created_at: datetime


class DataQualityReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    completeness_score: float
    validity_score: float
    consistency_score: float
    uniqueness_score: float
    overall_score: float
    created_at: datetime
    findings: list[DataQualityFindingRead]


class AnalyticsJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: AnalyticsJobStatus
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class ChannelPerformanceRead(BaseModel):
    dimension: str
    units_sold: float | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    units_returned: float | None = None
    return_rate: float | None = None


class AnalyticsSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    job_id: uuid.UUID
    row_count: int
    column_count: int
    mapped_field_count: int
    summary: str | None
    created_at: datetime


class AnalyticsSummaryResponse(BaseModel):
    """GET /analytics/summary - the latest snapshot's headline figures:
    KPIs, the data-quality overall score, and channel performance (the
    one grouped metric from the spec's 25 with no endpoint of its own).
    """

    snapshot: AnalyticsSnapshotRead
    kpis: list[KPIResultRead]
    data_quality_overall_score: float | None
    channel_performance: list[ChannelPerformanceRead]


class KPIsResponse(BaseModel):
    snapshot: AnalyticsSnapshotRead
    kpis: list[KPIResultRead]


class RunAnalyticsResponse(BaseModel):
    job: AnalyticsJobRead
    snapshot: AnalyticsSnapshotRead


class AnomalyFindingRead(BaseModel):
    anomaly_type: str
    severity: str
    entity: str
    metric: str
    value: float
    z_score: float
    description: str


class AnomaliesResponse(BaseModel):
    dataset_id: uuid.UUID
    anomalies: list[AnomalyFindingRead]


class TrendPointRead(BaseModel):
    period: str
    units_sold: float | None = None
    revenue: float | None = None


class TrendsResponse(BaseModel):
    dataset_id: uuid.UUID
    granularity: str
    points: list[TrendPointRead]


class ProductRankingRead(BaseModel):
    product_id: str
    product_name: str | None = None
    units_sold: float | None = None
    revenue: float | None = None


class ProductsResponse(BaseModel):
    dataset_id: uuid.UUID
    top_products: list[ProductRankingRead]
    worst_products: list[ProductRankingRead]


class DimensionPerformanceRead(BaseModel):
    dimension: str
    units_sold: float | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    units_returned: float | None = None
    return_rate: float | None = None


class CategoriesResponse(BaseModel):
    dataset_id: uuid.UUID
    categories: list[DimensionPerformanceRead]
    top_brands: list[DimensionPerformanceRead]


class SuppliersResponse(BaseModel):
    dataset_id: uuid.UUID
    suppliers: list[DimensionPerformanceRead]


class RegionsResponse(BaseModel):
    dataset_id: uuid.UUID
    regions: list[DimensionPerformanceRead]


class AnalyticsErrorDetail(BaseModel):
    """Structured error payload, mirroring DatasetErrorDetail so clients
    get a consistent shape across both dataset and analytics APIs."""

    code: str
    message: str
