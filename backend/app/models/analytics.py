"""Analytics ORM models: AnalyticsJob, AnalyticsSnapshot, KPIResult,
DataQualityReport, DataQualityFinding.

An AnalyticsJob records a single run of `POST /analytics/run` against a
dataset. On success it produces exactly one AnalyticsSnapshot, which is
the parent for that run's KPIResult rows (the 15 scalar KPIs - see
app/services/kpi_engine.py) and its DataQualityReport (with
DataQualityFinding rows). Ranking/grouping KPIs (top products, category
/supplier/regional/channel performance) and time-series trends and
anomalies are deliberately NOT persisted here - they support filters
(date range, category, supplier, region, channel) that a frozen snapshot
can't answer, so they're computed live from the dataset's normalized CSV
on every request instead (see app/services/analytics_service.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.dataset import FindingSeverity


class AnalyticsJobStatus(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class KPIName(enum.StrEnum):
    """The 15 scalar KPIs persisted per snapshot. Ranking/grouping KPIs
    (top products, category/supplier/regional/channel performance) and
    trends are computed live and are not part of this enum."""

    REVENUE = "revenue"
    GROSS_PROFIT = "gross_profit"
    GROSS_MARGIN = "gross_margin"
    AVERAGE_SELLING_PRICE = "average_selling_price"
    AVERAGE_ORDER_VALUE = "average_order_value"
    INVENTORY_VALUE = "inventory_value"
    INVENTORY_TURNOVER = "inventory_turnover"
    SELL_THROUGH_RATE = "sell_through_rate"
    RETURN_RATE = "return_rate"
    RETURN_COST = "return_cost"
    UNITS_SOLD = "units_sold"
    UNITS_RETURNED = "units_returned"
    STOCKOUTS = "stockouts"
    OVERSTOCK_COUNT = "overstock_count"
    LOW_INVENTORY_COUNT = "low_inventory_count"


class AnalyticsJob(Base):
    __tablename__ = "analytics_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    triggered_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AnalyticsJobStatus] = mapped_column(
        Enum(AnalyticsJobStatus, name="analytics_job_status", native_enum=True),
        nullable=False,
        default=AnalyticsJobStatus.RUNNING,
    )
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    snapshot: Mapped["AnalyticsSnapshot | None"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analytics_jobs.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mapped_field_count: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[AnalyticsJob] = relationship(back_populates="snapshot")
    kpi_results: Mapped[list["KPIResult"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", order_by="KPIResult.kpi_name"
    )
    quality_report: Mapped["DataQualityReport | None"] = relationship(
        back_populates="snapshot", uselist=False, cascade="all, delete-orphan"
    )


class KPIResult(Base):
    __tablename__ = "kpi_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analytics_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kpi_name: Mapped[KPIName] = mapped_column(
        Enum(KPIName, name="kpi_name", native_enum=True), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    snapshot: Mapped[AnalyticsSnapshot] = relationship(back_populates="kpi_results")


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analytics_snapshots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        unique=True,
    )
    completeness_score: Mapped[float] = mapped_column(Float, nullable=False)
    validity_score: Mapped[float] = mapped_column(Float, nullable=False)
    consistency_score: Mapped[float] = mapped_column(Float, nullable=False)
    uniqueness_score: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    snapshot: Mapped[AnalyticsSnapshot] = relationship(back_populates="quality_report")
    findings: Mapped[list["DataQualityFinding"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class DataQualityFinding(Base):
    __tablename__ = "data_quality_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_quality_reports.id", ondelete="CASCADE"), index=True, nullable=False
    )
    severity: Mapped[FindingSeverity] = mapped_column(
        Enum(FindingSeverity, name="dataset_finding_severity", native_enum=True), nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    report: Mapped[DataQualityReport] = relationship(back_populates="findings")
