"""Orchestration for the Phase 4 analytics API.

Ownership and readiness: every entry point here first calls
get_ready_dataset_or_404, which delegates ownership enforcement to
dataset_service.get_owned_dataset_or_404 (404, never 403, for a dataset
the caller doesn't own - see that module's docstring) and additionally
requires the dataset to be READY with a normalized file on disk, since
there is nothing to analyze otherwise.

Two call shapes, matching the persisted-vs-live split documented in
app/models/analytics.py:
- run_analytics() computes the 15 scalar KPIs (kpi_engine) and the data
  -quality scores/findings (data_quality), and persists them as a new
  AnalyticsJob + AnalyticsSnapshot + KPIResult rows + DataQualityReport
  (+ findings). get_summary/get_kpis/get_data_quality read back the
  latest snapshot - they never take filter params, since a persisted
  snapshot is a frozen point in time.
- get_anomalies/get_trends/get_products/get_categories/get_suppliers/
  get_regions recompute from the dataset's normalized CSV on every call
  via kpi_engine/anomaly_engine, honoring date_from/date_to/category/
  supplier/region/channel filters - never persisted.
"""

import uuid
from datetime import date

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud import analytics as analytics_crud
from app.crud import dataset as dataset_crud
from app.models.analytics import AnalyticsJob, AnalyticsSnapshot
from app.models.dataset import BusinessField, Dataset, DatasetColumn, DatasetStatus
from app.models.user import User
from app.services import anomaly_engine, data_quality, dataset_service, kpi_engine
from app.services.dataset_service import DatasetServiceError
from app.services.storage import resolve_storage_path

settings = get_settings()

ColumnMap = dict[BusinessField, str]
_DimensionPerformancePair = tuple[
    list[kpi_engine.DimensionPerformanceRecord], list[kpi_engine.DimensionPerformanceRecord]
]


async def get_ready_dataset_or_404(
    db: AsyncSession, dataset_id: uuid.UUID, current_user: User
) -> Dataset:
    dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
    if dataset.status != DatasetStatus.READY or not dataset.normalized_storage_path:
        raise DatasetServiceError(
            400,
            "DATASET_NOT_READY",
            "This dataset has no successfully validated data to analyze yet.",
        )
    return dataset


def _build_column_map(columns: list[DatasetColumn]) -> ColumnMap:
    return {c.mapped_business_field: c.normalized_name for c in columns if c.mapped_business_field}


def _load_dataframe(dataset: Dataset) -> pd.DataFrame:
    if dataset.normalized_storage_path is None:
        # Unreachable in practice: every caller obtains `dataset` via
        # get_ready_dataset_or_404, which already guarantees this.
        raise DatasetServiceError(400, "DATASET_NOT_READY", "Dataset has no normalized data.")
    path = resolve_storage_path(dataset.normalized_storage_path)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


async def _load_dataframe_and_column_map(
    db: AsyncSession, dataset: Dataset
) -> tuple[pd.DataFrame, ColumnMap]:
    columns = await dataset_crud.get_columns(db, dataset.id)
    return _load_dataframe(dataset), _build_column_map(columns)


def _apply_filters(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> pd.DataFrame:
    return kpi_engine.apply_filters(
        df,
        column_map,
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )


# --- Persisted (POST /analytics/run, GET /summary|/kpis|/data-quality) ----


async def run_analytics(
    db: AsyncSession, dataset: Dataset, current_user: User
) -> tuple[AnalyticsJob, AnalyticsSnapshot]:
    job = await analytics_crud.create_job(
        db, dataset_id=dataset.id, triggered_by_user_id=current_user.id
    )
    try:
        df, column_map = await _load_dataframe_and_column_map(db, dataset)

        kpi_values = kpi_engine.compute_all_scalar_kpis(
            df,
            column_map,
            overstock_multiple=settings.analytics_overstock_multiple,
            low_inventory_threshold=settings.analytics_low_inventory_threshold,
        )
        scores = data_quality.compute_quality_scores(df, column_map)
        quality_findings = data_quality.run_detection_rules(
            df, column_map, iqr_multiplier=settings.analytics_iqr_multiplier
        )

        summary = (
            f"{len(kpi_values)} KPI(s) computed; overall data quality "
            f"{scores.overall_score:.1f}/100."
        )
        snapshot = await analytics_crud.create_snapshot(
            db,
            dataset_id=dataset.id,
            job_id=job.id,
            row_count=len(df),
            column_count=len(df.columns),
            mapped_field_count=len(column_map),
            summary=summary,
        )
        await analytics_crud.add_kpi_results(db, snapshot.id, kpi_values)
        await analytics_crud.create_quality_report(
            db, snapshot_id=snapshot.id, scores=scores, findings=quality_findings
        )
        job = await analytics_crud.mark_job_completed(db, job)
    except Exception as exc:
        await analytics_crud.mark_job_failed(db, job, error_message=str(exc))
        raise

    refreshed = await analytics_crud.get_latest_snapshot(db, dataset.id)
    if refreshed is None:  # pragma: no cover - defensive, snapshot was just created above
        raise RuntimeError("Snapshot vanished immediately after creation.")
    return job, refreshed


async def get_latest_snapshot_or_404(db: AsyncSession, dataset: Dataset) -> AnalyticsSnapshot:
    snapshot = await analytics_crud.get_latest_snapshot(db, dataset.id)
    if snapshot is None:
        raise DatasetServiceError(
            404,
            "ANALYTICS_NOT_RUN",
            "No analytics have been computed for this dataset yet. Call POST /analytics/run first.",
        )
    return snapshot


async def get_channel_performance(
    db: AsyncSession, dataset: Dataset
) -> list[kpi_engine.DimensionPerformanceRecord]:
    df, column_map = await _load_dataframe_and_column_map(db, dataset)
    return kpi_engine.channel_performance(df, column_map, limit=settings.analytics_top_n)


# --- Live-computed (filterable) -------------------------------------------


async def get_anomalies(
    db: AsyncSession,
    dataset: Dataset,
    *,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> list[anomaly_engine.AnomalyFinding]:
    df, column_map = await _load_dataframe_and_column_map(db, dataset)
    filtered = _apply_filters(
        df,
        column_map,
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )
    return anomaly_engine.run_all_detectors(
        filtered,
        column_map,
        zscore_threshold=settings.analytics_zscore_threshold,
        iqr_multiplier=settings.analytics_iqr_multiplier,
    )


async def get_trends(
    db: AsyncSession,
    dataset: Dataset,
    *,
    granularity: str,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> list[kpi_engine.TrendPointRecord]:
    df, column_map = await _load_dataframe_and_column_map(db, dataset)
    filtered = _apply_filters(
        df,
        column_map,
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )
    return kpi_engine.compute_trends(filtered, column_map, granularity=granularity)


async def get_products(
    db: AsyncSession,
    dataset: Dataset,
    *,
    limit: int,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> tuple[list[kpi_engine.ProductRankingRecord], list[kpi_engine.ProductRankingRecord]]:
    df, column_map = await _load_dataframe_and_column_map(db, dataset)
    filtered = _apply_filters(
        df,
        column_map,
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )
    top = kpi_engine.product_ranking(filtered, column_map, limit=limit)
    worst = kpi_engine.product_ranking(filtered, column_map, limit=limit, worst=True)
    return top, worst


async def get_categories(
    db: AsyncSession,
    dataset: Dataset,
    *,
    limit: int,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> _DimensionPerformancePair:
    df, column_map = await _load_dataframe_and_column_map(db, dataset)
    filtered = _apply_filters(
        df,
        column_map,
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )
    categories = kpi_engine.category_performance(filtered, column_map, limit=limit)
    brands = kpi_engine.brand_performance(filtered, column_map, limit=limit)
    return categories, brands


async def get_suppliers(
    db: AsyncSession,
    dataset: Dataset,
    *,
    limit: int,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> list[kpi_engine.DimensionPerformanceRecord]:
    df, column_map = await _load_dataframe_and_column_map(db, dataset)
    filtered = _apply_filters(
        df,
        column_map,
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )
    return kpi_engine.supplier_performance(filtered, column_map, limit=limit)


async def get_regions(
    db: AsyncSession,
    dataset: Dataset,
    *,
    limit: int,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> list[kpi_engine.DimensionPerformanceRecord]:
    df, column_map = await _load_dataframe_and_column_map(db, dataset)
    filtered = _apply_filters(
        df,
        column_map,
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )
    return kpi_engine.regional_performance(filtered, column_map, limit=limit)
