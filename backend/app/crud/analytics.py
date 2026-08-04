"""Data-access helpers for the Phase 4 analytics tables."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analytics import (
    AnalyticsJob,
    AnalyticsJobStatus,
    AnalyticsSnapshot,
    DataQualityFinding,
    DataQualityReport,
    KPIName,
    KPIResult,
)
from app.models.dataset import FindingSeverity
from app.services.data_quality import QualityFinding, QualityScores
from app.services.kpi_engine import KPIValue


async def create_job(
    db: AsyncSession, *, dataset_id: uuid.UUID, triggered_by_user_id: uuid.UUID
) -> AnalyticsJob:
    job = AnalyticsJob(
        dataset_id=dataset_id,
        triggered_by_user_id=triggered_by_user_id,
        status=AnalyticsJobStatus.RUNNING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def mark_job_completed(db: AsyncSession, job: AnalyticsJob) -> AnalyticsJob:
    job.status = AnalyticsJobStatus.COMPLETED
    job.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(job)
    return job


async def mark_job_failed(
    db: AsyncSession, job: AnalyticsJob, *, error_message: str
) -> AnalyticsJob:
    job.status = AnalyticsJobStatus.FAILED
    job.error_message = error_message
    job.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(job)
    return job


async def create_snapshot(
    db: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    job_id: uuid.UUID,
    row_count: int,
    column_count: int,
    mapped_field_count: int,
    summary: str | None,
) -> AnalyticsSnapshot:
    snapshot = AnalyticsSnapshot(
        dataset_id=dataset_id,
        job_id=job_id,
        row_count=row_count,
        column_count=column_count,
        mapped_field_count=mapped_field_count,
        summary=summary,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def add_kpi_results(
    db: AsyncSession, snapshot_id: uuid.UUID, kpi_values: dict[str, KPIValue]
) -> list[KPIResult]:
    created: list[KPIResult] = []
    for name, kpi_value in kpi_values.items():
        result = KPIResult(
            snapshot_id=snapshot_id,
            kpi_name=KPIName(name),
            value=kpi_value.value,
            unit=kpi_value.unit,
        )
        db.add(result)
        created.append(result)
    await db.commit()
    for result in created:
        await db.refresh(result)
    return created


async def create_quality_report(
    db: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    scores: QualityScores,
    findings: list[QualityFinding],
) -> DataQualityReport:
    report = DataQualityReport(
        snapshot_id=snapshot_id,
        completeness_score=scores.completeness_score,
        validity_score=scores.validity_score,
        consistency_score=scores.consistency_score,
        uniqueness_score=scores.uniqueness_score,
        overall_score=scores.overall_score,
    )
    db.add(report)
    await db.flush()

    for finding in findings:
        db.add(
            DataQualityFinding(
                report_id=report.id,
                severity=FindingSeverity(finding.severity),
                category=finding.category,
                description=finding.description,
                recommendation=finding.recommendation,
            )
        )

    await db.commit()
    await db.refresh(report)
    return report


async def get_latest_snapshot(db: AsyncSession, dataset_id: uuid.UUID) -> AnalyticsSnapshot | None:
    """The most recent snapshot for a dataset, with KPIs and the
    data-quality report (plus its findings) eagerly loaded so callers
    can read them after this coroutine returns without triggering a
    lazy-load on the async session."""
    result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.dataset_id == dataset_id)
        .options(
            selectinload(AnalyticsSnapshot.kpi_results),
            selectinload(AnalyticsSnapshot.quality_report).selectinload(DataQualityReport.findings),
        )
        .order_by(AnalyticsSnapshot.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_job_by_id(db: AsyncSession, job_id: uuid.UUID) -> AnalyticsJob | None:
    result = await db.execute(select(AnalyticsJob).where(AnalyticsJob.id == job_id))
    return result.scalar_one_or_none()
