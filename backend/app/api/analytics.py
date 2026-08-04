"""Analytics endpoints: run analysis, read KPIs/data-quality/summary from
the latest persisted snapshot, and live-compute anomalies/trends/product
rankings/category/supplier/region performance with filters.

Endpoint paths match the Phase 4 spec exactly (GET /analytics/summary,
GET /analytics/kpis, ... POST /analytics/run) - `dataset_id` is passed
as a required query parameter rather than a path segment, since the
dataset a request applies to isn't part of these ten fixed paths.

All endpoints require authentication and dataset ownership, enforced via
analytics_service.get_ready_dataset_or_404 (delegates to
dataset_service.get_owned_dataset_or_404 - 404, never 403, for a dataset
the caller doesn't own) plus a READY-with-normalized-data check.
"""

import uuid
from datetime import date
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsErrorDetail,
    AnalyticsJobRead,
    AnalyticsSnapshotRead,
    AnomaliesResponse,
    AnomalyFindingRead,
    CategoriesResponse,
    DataQualityReportRead,
    DimensionPerformanceRead,
    KPIResultRead,
    KPIsResponse,
    ProductRankingRead,
    ProductsResponse,
    RegionsResponse,
    RunAnalyticsResponse,
    SuppliersResponse,
    TrendPointRead,
    TrendsResponse,
)
from app.schemas.analytics import AnalyticsSummaryResponse as SummaryResponse
from app.schemas.analytics import ChannelPerformanceRead as ChannelRead
from app.services import analytics_service, kpi_engine
from app.services.dataset_service import DatasetServiceError

router = APIRouter(prefix="/analytics", tags=["analytics"])

settings = get_settings()

_DatasetIdQuery = Query(..., description="The dataset this analytics request applies to.")


def _raise_service_error(exc: DatasetServiceError) -> None:
    detail = AnalyticsErrorDetail(code=exc.code, message=exc.message)
    raise HTTPException(status_code=exc.status_code, detail=detail.model_dump(mode="json"))


def _dimension_performance_read(
    row: kpi_engine.DimensionPerformanceRecord,
) -> DimensionPerformanceRead:
    return DimensionPerformanceRead(
        dimension=row["dimension"],
        units_sold=row["units_sold"],
        revenue=row["revenue"],
        gross_profit=row["gross_profit"],
        units_returned=row["units_returned"],
        return_rate=row["return_rate"],
    )


class _FilterKwargs(TypedDict):
    """Precise per-field shape for the date/category/supplier/region/channel
    filters shared by every live-computed endpoint below. A plain
    `dict[str, date | str | None]` would widen every value to that whole
    union, which mypy then rejects when it's `**`-unpacked into
    analytics_service functions whose keyword parameters are individually
    typed narrower (e.g. `date_from: date | None`, `category: str | None`).
    A TypedDict is unpacked key-by-key against the matching parameter
    instead, so each field keeps its own precise type - same dict at
    runtime, nothing here changes what's passed to those functions."""

    date_from: date | None
    date_to: date | None
    category: str | None
    supplier: str | None
    region: str | None
    channel: str | None


def _filter_kwargs(
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    supplier: str | None,
    region: str | None,
    channel: str | None,
) -> _FilterKwargs:
    return _FilterKwargs(
        date_from=date_from,
        date_to=date_to,
        category=category,
        supplier=supplier,
        region=region,
        channel=channel,
    )


@router.post("/run", response_model=RunAnalyticsResponse)
async def run_analytics(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunAnalyticsResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        job, snapshot = await analytics_service.run_analytics(db, dataset, current_user)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return RunAnalyticsResponse(
        job=AnalyticsJobRead.model_validate(job),
        snapshot=AnalyticsSnapshotRead.model_validate(snapshot),
    )


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SummaryResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        snapshot = await analytics_service.get_latest_snapshot_or_404(db, dataset)
        channel_rows = await analytics_service.get_channel_performance(db, dataset)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return SummaryResponse(
        snapshot=AnalyticsSnapshotRead.model_validate(snapshot),
        kpis=[KPIResultRead.model_validate(k) for k in snapshot.kpi_results],
        data_quality_overall_score=(
            snapshot.quality_report.overall_score if snapshot.quality_report else None
        ),
        channel_performance=[
            ChannelRead(
                dimension=row["dimension"],
                units_sold=row["units_sold"],
                revenue=row["revenue"],
                gross_profit=row["gross_profit"],
                units_returned=row["units_returned"],
                return_rate=row["return_rate"],
            )
            for row in channel_rows
        ],
    )


@router.get("/kpis", response_model=KPIsResponse)
async def get_kpis(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KPIsResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        snapshot = await analytics_service.get_latest_snapshot_or_404(db, dataset)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return KPIsResponse(
        snapshot=AnalyticsSnapshotRead.model_validate(snapshot),
        kpis=[KPIResultRead.model_validate(k) for k in snapshot.kpi_results],
    )


@router.get("/data-quality", response_model=DataQualityReportRead)
async def get_data_quality(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataQualityReportRead:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        snapshot = await analytics_service.get_latest_snapshot_or_404(db, dataset)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    if snapshot.quality_report is None:
        _raise_service_error(
            DatasetServiceError(
                404, "DATA_QUALITY_NOT_FOUND", "No data-quality report on the latest snapshot."
            )
        )
        raise  # unreachable, satisfies type checkers

    return DataQualityReportRead.model_validate(snapshot.quality_report)


@router.get("/anomalies", response_model=AnomaliesResponse)
async def get_anomalies(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    region: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnomaliesResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        findings = await analytics_service.get_anomalies(
            db,
            dataset,
            **_filter_kwargs(date_from, date_to, category, supplier, region, channel),
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return AnomaliesResponse(
        dataset_id=dataset_id,
        anomalies=[
            AnomalyFindingRead(
                anomaly_type=f.anomaly_type,
                severity=f.severity,
                entity=f.entity,
                metric=f.metric,
                value=f.value,
                z_score=f.z_score,
                description=f.description,
            )
            for f in findings
        ],
    )


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    granularity: str = Query(default="monthly", pattern="^(daily|weekly|monthly)$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    region: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrendsResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        points = await analytics_service.get_trends(
            db,
            dataset,
            granularity=granularity,
            **_filter_kwargs(date_from, date_to, category, supplier, region, channel),
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return TrendsResponse(
        dataset_id=dataset_id,
        granularity=granularity,
        points=[
            TrendPointRead(period=p["period"], units_sold=p["units_sold"], revenue=p["revenue"])
            for p in points
        ],
    )


@router.get("/products", response_model=ProductsResponse)
async def get_products(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    limit: int | None = Query(default=None, ge=1, le=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    region: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductsResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        top, worst = await analytics_service.get_products(
            db,
            dataset,
            limit=limit or settings.analytics_top_n,
            **_filter_kwargs(date_from, date_to, category, supplier, region, channel),
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return ProductsResponse(
        dataset_id=dataset_id,
        top_products=[
            ProductRankingRead(
                product_id=p["product_id"],
                product_name=p["product_name"],
                units_sold=p["units_sold"],
                revenue=p["revenue"],
            )
            for p in top
        ],
        worst_products=[
            ProductRankingRead(
                product_id=p["product_id"],
                product_name=p["product_name"],
                units_sold=p["units_sold"],
                revenue=p["revenue"],
            )
            for p in worst
        ],
    )


@router.get("/categories", response_model=CategoriesResponse)
async def get_categories(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    limit: int | None = Query(default=None, ge=1, le=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    region: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CategoriesResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        categories, brands = await analytics_service.get_categories(
            db,
            dataset,
            limit=limit or settings.analytics_top_n,
            **_filter_kwargs(date_from, date_to, category, supplier, region, channel),
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return CategoriesResponse(
        dataset_id=dataset_id,
        categories=[_dimension_performance_read(c) for c in categories],
        top_brands=[_dimension_performance_read(b) for b in brands],
    )


@router.get("/suppliers", response_model=SuppliersResponse)
async def get_suppliers(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    limit: int | None = Query(default=None, ge=1, le=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    region: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SuppliersResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        suppliers = await analytics_service.get_suppliers(
            db,
            dataset,
            limit=limit or settings.analytics_top_n,
            **_filter_kwargs(date_from, date_to, category, supplier, region, channel),
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return SuppliersResponse(
        dataset_id=dataset_id,
        suppliers=[_dimension_performance_read(s) for s in suppliers],
    )


@router.get("/regions", response_model=RegionsResponse)
async def get_regions(
    dataset_id: uuid.UUID = _DatasetIdQuery,
    limit: int | None = Query(default=None, ge=1, le=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    region: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RegionsResponse:
    try:
        dataset = await analytics_service.get_ready_dataset_or_404(db, dataset_id, current_user)
        regions = await analytics_service.get_regions(
            db,
            dataset,
            limit=limit or settings.analytics_top_n,
            **_filter_kwargs(date_from, date_to, category, supplier, region, channel),
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return RegionsResponse(
        dataset_id=dataset_id,
        regions=[_dimension_performance_read(r) for r in regions],
    )
