"""Data-access helpers for dataset ingestion tables."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import (
    AuditEventType,
    BusinessField,
    Dataset,
    DatasetAuditEvent,
    DatasetColumn,
    DatasetFileType,
    DatasetStatus,
    DatasetUpload,
    DatasetValidationFinding,
    DatasetValidationRun,
    FindingSeverity,
    UploadStatus,
    ValidationRunStatus,
)
from app.services.dataset_ingestion import ColumnResult, Finding


async def create_dataset(
    db: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    original_filename: str,
    stored_filename: str,
    display_name: str,
    file_type: DatasetFileType,
    file_size_bytes: int,
    storage_path: str,
) -> Dataset:
    dataset = Dataset(
        id=dataset_id,
        owner_user_id=owner_user_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        display_name=display_name,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        status=DatasetStatus.UPLOADED,
        storage_path=storage_path,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def get_dataset_by_id(db: AsyncSession, dataset_id: uuid.UUID) -> Dataset | None:
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    return result.scalar_one_or_none()


async def list_datasets(db: AsyncSession, *, owner_user_id: uuid.UUID | None) -> list[Dataset]:
    query = select(Dataset).where(Dataset.status != DatasetStatus.DELETED)
    if owner_user_id is not None:
        query = query.where(Dataset.owner_user_id == owner_user_id)
    query = query.order_by(Dataset.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_display_name(db: AsyncSession, dataset: Dataset, display_name: str) -> Dataset:
    dataset.display_name = display_name
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def mark_validating(db: AsyncSession, dataset: Dataset) -> Dataset:
    dataset.status = DatasetStatus.VALIDATING
    dataset.error_message = None
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def mark_ready(
    db: AsyncSession,
    dataset: Dataset,
    *,
    row_count: int,
    column_count: int,
    normalized_storage_path: str,
) -> Dataset:
    dataset.status = DatasetStatus.READY
    dataset.row_count = row_count
    dataset.column_count = column_count
    dataset.normalized_storage_path = normalized_storage_path
    dataset.error_message = None
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def mark_failed(db: AsyncSession, dataset: Dataset, *, error_message: str) -> Dataset:
    dataset.status = DatasetStatus.FAILED
    dataset.error_message = error_message
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def mark_deleted(db: AsyncSession, dataset: Dataset) -> Dataset:
    dataset.status = DatasetStatus.DELETED
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def replace_columns(
    db: AsyncSession, dataset_id: uuid.UUID, columns: list[ColumnResult]
) -> list[DatasetColumn]:
    existing = await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id))
    for row in existing.scalars().all():
        await db.delete(row)
    await db.flush()

    created: list[DatasetColumn] = []
    for column in columns:
        db_column = DatasetColumn(
            dataset_id=dataset_id,
            source_name=column.source_name,
            normalized_name=column.normalized_name,
            position=column.position,
            inferred_type=column.inferred_type,
            nullable=column.nullable,
            sample_values=column.sample_values,
        )
        db.add(db_column)
        created.append(db_column)

    await db.commit()
    for db_column in created:
        await db.refresh(db_column)
    return created


async def get_columns(db: AsyncSession, dataset_id: uuid.UUID) -> list[DatasetColumn]:
    result = await db.execute(
        select(DatasetColumn)
        .where(DatasetColumn.dataset_id == dataset_id)
        .order_by(DatasetColumn.position)
    )
    return list(result.scalars().all())


async def get_column_by_id(db: AsyncSession, column_id: uuid.UUID) -> DatasetColumn | None:
    result = await db.execute(select(DatasetColumn).where(DatasetColumn.id == column_id))
    return result.scalar_one_or_none()


async def set_column_mapping(
    db: AsyncSession, column: DatasetColumn, business_field: BusinessField | None
) -> DatasetColumn:
    column.mapped_business_field = business_field
    await db.commit()
    await db.refresh(column)
    return column


async def create_upload_record(
    db: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
    original_filename: str,
    file_size_bytes: int,
    file_type: DatasetFileType,
    upload_status: UploadStatus,
    error_message: str | None = None,
) -> DatasetUpload:
    upload = DatasetUpload(
        dataset_id=dataset_id,
        uploaded_by_user_id=uploaded_by_user_id,
        original_filename=original_filename,
        file_size_bytes=file_size_bytes,
        file_type=file_type,
        upload_status=upload_status,
        error_message=error_message,
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)
    return upload


async def create_validation_run(
    db: AsyncSession, *, dataset_id: uuid.UUID, triggered_by_user_id: uuid.UUID
) -> DatasetValidationRun:
    run = DatasetValidationRun(
        dataset_id=dataset_id,
        triggered_by_user_id=triggered_by_user_id,
        status=ValidationRunStatus.RUNNING,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def complete_validation_run(
    db: AsyncSession,
    run: DatasetValidationRun,
    *,
    status: ValidationRunStatus,
    row_count: int | None,
    column_count: int | None,
    summary: str | None,
    findings: list[Finding],
) -> DatasetValidationRun:
    run.status = status
    run.row_count = row_count
    run.column_count = column_count
    run.summary = summary
    run.completed_at = datetime.now(UTC)

    for finding in findings:
        db.add(
            DatasetValidationFinding(
                validation_run_id=run.id,
                severity=FindingSeverity(finding.severity),
                code=finding.code,
                message=finding.message,
                row_number=finding.row_number,
                column_name=finding.column_name,
            )
        )

    await db.commit()
    await db.refresh(run)
    return run


async def get_latest_validation_run(
    db: AsyncSession, dataset_id: uuid.UUID
) -> DatasetValidationRun | None:
    result = await db.execute(
        select(DatasetValidationRun)
        .where(DatasetValidationRun.dataset_id == dataset_id)
        .order_by(DatasetValidationRun.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_audit_event(
    db: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    user_id: uuid.UUID,
    event_type: AuditEventType,
    message: str | None = None,
) -> DatasetAuditEvent:
    event = DatasetAuditEvent(
        dataset_id=dataset_id, user_id=user_id, event_type=event_type, message=message
    )
    db.add(event)
    await db.commit()
    return event
