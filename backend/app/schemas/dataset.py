"""Pydantic schemas for dataset upload, listing, preview, and mapping."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.dataset import (
    BusinessField,
    ColumnDataType,
    DatasetFileType,
    DatasetStatus,
    FindingSeverity,
    ValidationRunStatus,
)


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    display_name: str
    original_filename: str
    file_type: DatasetFileType
    file_size_bytes: int
    row_count: int | None
    column_count: int | None
    status: DatasetStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DatasetUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class DatasetColumnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_name: str
    normalized_name: str
    position: int
    inferred_type: ColumnDataType
    nullable: bool
    sample_values: list[str]
    mapped_business_field: BusinessField | None
    created_at: datetime


class DatasetColumnsResponse(BaseModel):
    columns: list[DatasetColumnRead]
    available_analyses: list[str]


class ColumnMappingItem(BaseModel):
    column_id: uuid.UUID
    # Explicit null clears an existing mapping. Omitting a column from the
    # request list simply leaves that column's mapping unchanged.
    mapped_business_field: BusinessField | None = None


class ColumnMappingUpdate(BaseModel):
    columns: list[ColumnMappingItem] = Field(min_length=1)


class DatasetPreviewResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    returned_row_count: int
    total_row_count: int | None


class ValidationFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity: FindingSeverity
    code: str
    message: str
    row_number: int | None
    column_name: str | None


class ValidationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ValidationRunStatus
    row_count: int | None
    column_count: int | None
    summary: str | None
    started_at: datetime
    completed_at: datetime | None
    findings: list[ValidationFindingRead]


class DatasetErrorDetail(BaseModel):
    """Structured error payload used as HTTPException(detail=...) for
    dataset validation failures, so clients get a machine-readable code
    plus a list of specific findings rather than one flat string.
    """

    code: str
    message: str
    findings: list[ValidationFindingRead] = Field(default_factory=list)
