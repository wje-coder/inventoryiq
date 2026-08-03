"""Business logic for dataset ingestion: ownership enforcement, upload
orchestration, (re)validation, preview, column mapping, and deletion.

Ownership rule: a non-admin user gets a 404 (not 403) for any dataset
they don't own, so the API never confirms whether a given dataset ID
belongs to someone else.
"""

import uuid
from pathlib import Path

import pandas as pd
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud import dataset as dataset_crud
from app.models.dataset import (
    AuditEventType,
    BusinessField,
    Dataset,
    DatasetColumn,
    DatasetFileType,
    DatasetStatus,
    FindingSeverity,
    UploadStatus,
    ValidationRunStatus,
)
from app.models.user import Role, User
from app.schemas.dataset import ColumnMappingItem
from app.services import storage
from app.services.dataset_ingestion import Finding, IngestionError, ingest_dataset_file

settings = get_settings()

_ALLOWED_EXTENSIONS = {"csv": DatasetFileType.CSV, "xlsx": DatasetFileType.XLSX}

# (analysis name, business fields required to unlock it)
_ANALYSIS_RULES: list[tuple[str, frozenset[BusinessField]]] = [
    (
        "Revenue trend analysis",
        frozenset(
            {BusinessField.ORDER_DATE, BusinessField.QUANTITY_SOLD, BusinessField.SALE_PRICE}
        ),
    ),
    ("Margin analysis", frozenset({BusinessField.UNIT_COST, BusinessField.RETAIL_PRICE})),
    (
        "Return rate analysis",
        frozenset({BusinessField.PRODUCT_ID, BusinessField.QUANTITY_RETURNED}),
    ),
    (
        "Regional demand analysis",
        frozenset({BusinessField.REGION, BusinessField.QUANTITY_SOLD}),
    ),
    (
        "Channel performance analysis",
        frozenset({BusinessField.CHANNEL, BusinessField.QUANTITY_SOLD}),
    ),
    (
        "Inventory health / stockout analysis",
        frozenset({BusinessField.PRODUCT_ID, BusinessField.QUANTITY_AVAILABLE}),
    ),
    (
        "Product catalog completeness",
        frozenset({BusinessField.PRODUCT_ID, BusinessField.PRODUCT_NAME, BusinessField.CATEGORY}),
    ),
    ("Supplier performance analysis", frozenset({BusinessField.SUPPLIER, BusinessField.UNIT_COST})),
    (
        "Customer order history",
        frozenset({BusinessField.CUSTOMER_ID, BusinessField.ORDER_ID, BusinessField.ORDER_DATE}),
    ),
    (
        "Discount / pricing anomaly detection",
        frozenset({BusinessField.RETAIL_PRICE, BusinessField.SALE_PRICE}),
    ),
]


class DatasetServiceError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, findings: list[Finding] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.findings = findings or []


def available_analyses(mapped_fields: set[BusinessField]) -> list[str]:
    return [name for name, required in _ANALYSIS_RULES if required.issubset(mapped_fields)]


async def get_owned_dataset_or_404(
    db: AsyncSession, dataset_id: uuid.UUID, current_user: User
) -> Dataset:
    dataset = await dataset_crud.get_dataset_by_id(db, dataset_id)
    is_owner = dataset is not None and dataset.owner_user_id == current_user.id
    is_admin = current_user.role == Role.ADMIN
    if dataset is None or dataset.status == DatasetStatus.DELETED or not (is_owner or is_admin):
        raise DatasetServiceError(404, "DATASET_NOT_FOUND", "Dataset not found.")
    return dataset


def _detect_file_type(filename: str) -> DatasetFileType:
    extension = Path(filename).suffix.lower().lstrip(".")
    file_type = _ALLOWED_EXTENSIONS.get(extension)
    if file_type is None:
        raise DatasetServiceError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "Only .csv and .xlsx files are supported.",
        )
    return file_type


async def _run_ingestion_and_persist(
    db: AsyncSession,
    dataset: Dataset,
    current_user: User,
    *,
    raise_on_failure: bool = False,
) -> Dataset:
    """Parse+validate the dataset's already-stored file, persist the
    outcome (columns, status, findings, audit event), and return the
    refreshed dataset.

    On a validation failure the dataset row is always kept (status
    "failed", with the error and findings recorded) so the failure stays
    visible and auditable - but any file already written for it (the
    original upload, and a normalized file if one happened to be written
    before a later failure) is removed from disk, so a failed ingestion
    never leaves an orphaned file behind.

    `raise_on_failure` controls whether a validation failure also raises
    a DatasetServiceError(400) back to the caller, in addition to being
    persisted. The initial synchronous upload passes True: an upload that
    fails validation must itself fail the HTTP request with 400, not
    report 201 with a "failed" body. An explicit POST
    /datasets/{id}/validate re-validation passes False (the default):
    that endpoint's job is to *run* validation, and a "failed" outcome is
    still a successful response describing that outcome.
    """
    dataset = await dataset_crud.mark_validating(db, dataset)
    run = await dataset_crud.create_validation_run(
        db, dataset_id=dataset.id, triggered_by_user_id=current_user.id
    )
    await dataset_crud.create_audit_event(
        db,
        dataset_id=dataset.id,
        user_id=current_user.id,
        event_type=AuditEventType.VALIDATION_STARTED,
    )

    source_path = storage.resolve_storage_path(dataset.storage_path)
    normalized_relative = str(
        storage.dataset_relative_dir(dataset.id) / f"{dataset.stored_filename}.normalized.csv"
    )
    normalized_path = storage.resolve_storage_path(normalized_relative)

    try:
        result = ingest_dataset_file(source_path, dataset.file_type, normalized_path)
    except IngestionError as exc:
        # The original file was written to disk before validation ran (and
        # ingest_dataset_file may have written a normalized file before
        # hitting a later failure); neither should survive a failed
        # ingestion. dataset_crud.mark_failed still keeps the dataset row
        # itself, so the failure remains auditable.
        storage.delete_file(dataset.storage_path)
        storage.delete_file(normalized_relative)

        dataset = await dataset_crud.mark_failed(db, dataset, error_message=exc.message)
        findings = [Finding(FindingSeverity.ERROR, exc.code, exc.message), *exc.findings]
        await dataset_crud.complete_validation_run(
            db,
            run,
            status=ValidationRunStatus.FAILED,
            row_count=None,
            column_count=None,
            summary=exc.message,
            findings=findings,
        )
        await dataset_crud.create_audit_event(
            db,
            dataset_id=dataset.id,
            user_id=current_user.id,
            event_type=AuditEventType.VALIDATION_FAILED,
            message=exc.message,
        )
        if raise_on_failure:
            raise DatasetServiceError(400, exc.code, exc.message, findings=findings) from exc
        return dataset

    await dataset_crud.replace_columns(db, dataset.id, result.columns)
    dataset = await dataset_crud.mark_ready(
        db,
        dataset,
        row_count=result.row_count,
        column_count=result.column_count,
        normalized_storage_path=normalized_relative,
    )
    await dataset_crud.complete_validation_run(
        db,
        run,
        status=ValidationRunStatus.PASSED,
        row_count=result.row_count,
        column_count=result.column_count,
        summary=f"{result.row_count} rows, {result.column_count} columns.",
        findings=result.findings,
    )
    await dataset_crud.create_audit_event(
        db,
        dataset_id=dataset.id,
        user_id=current_user.id,
        event_type=AuditEventType.VALIDATION_PASSED,
    )
    return dataset


async def process_upload(
    db: AsyncSession, current_user: User, upload_file: UploadFile, display_name: str | None
) -> Dataset:
    original_name = upload_file.filename or "upload"
    file_type = _detect_file_type(original_name)

    sanitized_name = storage.sanitize_original_filename(original_name)
    stored_filename = storage.generate_stored_filename(file_type.value)
    dataset_id = uuid.uuid4()
    relative_storage_path = str(storage.dataset_relative_dir(dataset_id) / stored_filename)

    try:
        bytes_written = await storage.save_upload_stream(upload_file, relative_storage_path)
    except storage.FileTooLargeError as exc:
        raise DatasetServiceError(413, "FILE_TOO_LARGE", str(exc)) from exc

    if bytes_written == 0:
        storage.delete_file(relative_storage_path)
        raise DatasetServiceError(400, "EMPTY_FILE", "The uploaded file is empty.")

    dataset = await dataset_crud.create_dataset(
        db,
        dataset_id=dataset_id,
        owner_user_id=current_user.id,
        original_filename=sanitized_name,
        stored_filename=stored_filename,
        display_name=(display_name or sanitized_name).strip() or sanitized_name,
        file_type=file_type,
        file_size_bytes=bytes_written,
        storage_path=relative_storage_path,
    )
    await dataset_crud.create_upload_record(
        db,
        dataset_id=dataset.id,
        uploaded_by_user_id=current_user.id,
        original_filename=sanitized_name,
        file_size_bytes=bytes_written,
        file_type=file_type,
        upload_status=UploadStatus.STORED,
    )
    await dataset_crud.create_audit_event(
        db, dataset_id=dataset.id, user_id=current_user.id, event_type=AuditEventType.UPLOADED
    )

    return await _run_ingestion_and_persist(db, dataset, current_user, raise_on_failure=True)


async def revalidate_dataset(db: AsyncSession, dataset: Dataset, current_user: User) -> Dataset:
    return await _run_ingestion_and_persist(db, dataset, current_user)


async def update_display_name(
    db: AsyncSession, dataset: Dataset, display_name: str, current_user: User
) -> Dataset:
    dataset = await dataset_crud.update_display_name(db, dataset, display_name)
    await dataset_crud.create_audit_event(
        db,
        dataset_id=dataset.id,
        user_id=current_user.id,
        event_type=AuditEventType.DISPLAY_NAME_UPDATED,
        message=f"Renamed to '{display_name}'.",
    )
    return dataset


async def update_column_mappings(
    db: AsyncSession, dataset: Dataset, items: list[ColumnMappingItem], current_user: User
) -> list[DatasetColumn]:
    existing_columns = {c.id: c for c in await dataset_crud.get_columns(db, dataset.id)}

    for item in items:
        column = existing_columns.get(item.column_id)
        if column is None:
            raise DatasetServiceError(
                404,
                "COLUMN_NOT_FOUND",
                f"Column {item.column_id} does not belong to this dataset.",
            )
        await dataset_crud.set_column_mapping(db, column, item.mapped_business_field)

    await dataset_crud.create_audit_event(
        db,
        dataset_id=dataset.id,
        user_id=current_user.id,
        event_type=AuditEventType.COLUMNS_MAPPED,
    )
    return await dataset_crud.get_columns(db, dataset.id)


def get_preview(dataset: Dataset) -> tuple[list[str], list[dict[str, str]]]:
    if dataset.status != DatasetStatus.READY or not dataset.normalized_storage_path:
        return [], []

    path = storage.resolve_storage_path(dataset.normalized_storage_path)
    limit = settings.dataset_preview_row_limit
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, nrows=limit)
    columns = list(frame.columns)
    rows = frame.to_dict(orient="records")
    return columns, rows


async def delete_dataset(db: AsyncSession, dataset: Dataset, current_user: User) -> Dataset:
    storage.delete_file(dataset.storage_path)
    storage.delete_file(dataset.normalized_storage_path)
    dataset = await dataset_crud.mark_deleted(db, dataset)
    await dataset_crud.create_audit_event(
        db, dataset_id=dataset.id, user_id=current_user.id, event_type=AuditEventType.DELETED
    )
    return dataset
