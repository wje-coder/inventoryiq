"""Dataset ingestion ORM models: Dataset, DatasetColumn, DatasetUpload,
DatasetValidationRun, DatasetValidationFinding, DatasetAuditEvent.

Row data itself is intentionally NOT stored one-row-per-record in
Postgres here (see app/services/dataset_ingestion.py for the rationale);
these tables hold metadata, schema, validation results, and audit trail.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DatasetStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class DatasetFileType(enum.StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


class ColumnDataType(enum.StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UNKNOWN = "unknown"


class BusinessField(enum.StrEnum):
    PRODUCT_ID = "product_id"
    SKU = "sku"
    UPC = "upc"
    PRODUCT_NAME = "product_name"
    CATEGORY = "category"
    BRAND = "brand"
    SUPPLIER = "supplier"
    UNIT_COST = "unit_cost"
    RETAIL_PRICE = "retail_price"
    SALE_PRICE = "sale_price"
    QUANTITY_AVAILABLE = "quantity_available"
    QUANTITY_SOLD = "quantity_sold"
    QUANTITY_RETURNED = "quantity_returned"
    ORDER_ID = "order_id"
    ORDER_DATE = "order_date"
    RETURN_DATE = "return_date"
    CUSTOMER_ID = "customer_id"
    REGION = "region"
    CHANNEL = "channel"
    STATUS = "status"


class UploadStatus(enum.StrEnum):
    RECEIVED = "received"
    STORED = "stored"
    FAILED = "failed"


class ValidationRunStatus(enum.StrEnum):
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class FindingSeverity(enum.StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AuditEventType(enum.StrEnum):
    UPLOADED = "uploaded"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    DELETED = "deleted"
    COLUMNS_MAPPED = "columns_mapped"
    DISPLAY_NAME_UPDATED = "display_name_updated"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Sanitized (no path separators/control chars) but otherwise the
    # user's original filename, kept for display only - never used to
    # build a filesystem path. See app/services/storage.py.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Randomly generated on-disk filename (uuid4 + original extension).
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    file_type: Mapped[DatasetFileType] = mapped_column(
        Enum(DatasetFileType, name="dataset_file_type", native_enum=True), nullable=False
    )
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[DatasetStatus] = mapped_column(
        Enum(DatasetStatus, name="dataset_status", native_enum=True),
        nullable=False,
        default=DatasetStatus.UPLOADED,
    )

    # Both paths are relative to settings.dataset_storage_dir - never
    # absolute, never exposed in API responses.
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Generic, safe-to-display message only (no stack traces, no paths).
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    columns: Mapped[list["DatasetColumn"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetColumn.position"
    )


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )

    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    inferred_type: Mapped[ColumnDataType] = mapped_column(
        Enum(ColumnDataType, name="dataset_column_type", native_enum=True),
        nullable=False,
        default=ColumnDataType.UNKNOWN,
    )
    nullable: Mapped[bool] = mapped_column(nullable=False, default=True)
    sample_values: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    mapped_business_field: Mapped[BusinessField | None] = mapped_column(
        Enum(BusinessField, name="dataset_business_field", native_enum=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset: Mapped["Dataset"] = relationship(back_populates="columns")


class DatasetUpload(Base):
    __tablename__ = "dataset_uploads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[DatasetFileType] = mapped_column(
        Enum(DatasetFileType, name="dataset_file_type", native_enum=True), nullable=False
    )

    upload_status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="dataset_upload_status", native_enum=True),
        nullable=False,
        default=UploadStatus.RECEIVED,
    )
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DatasetValidationRun(Base):
    __tablename__ = "dataset_validation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    triggered_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[ValidationRunStatus] = mapped_column(
        Enum(ValidationRunStatus, name="dataset_validation_run_status", native_enum=True),
        nullable=False,
        default=ValidationRunStatus.RUNNING,
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    findings: Mapped[list["DatasetValidationFinding"]] = relationship(
        back_populates="validation_run", cascade="all, delete-orphan"
    )


class DatasetValidationFinding(Base):
    __tablename__ = "dataset_validation_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_validation_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )

    severity: Mapped[FindingSeverity] = mapped_column(
        Enum(FindingSeverity, name="dataset_finding_severity", native_enum=True), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    validation_run: Mapped["DatasetValidationRun"] = relationship(back_populates="findings")


class DatasetAuditEvent(Base):
    __tablename__ = "dataset_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(AuditEventType, name="dataset_audit_event_type", native_enum=True), nullable=False
    )
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
