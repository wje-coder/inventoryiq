"""Dataset upload, listing, preview, column mapping, and deletion endpoints.

All endpoints require authentication (app.api.deps.get_current_user).
Ownership is enforced per-request via
dataset_service.get_owned_dataset_or_404, which returns 404 (not 403)
for datasets the caller doesn't own and isn't an admin for, so the API
never confirms that another user's dataset exists.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.crud import dataset as dataset_crud
from app.db.session import get_db
from app.models.dataset import DatasetColumn
from app.models.user import Role, User
from app.schemas.dataset import (
    ColumnMappingUpdate,
    DatasetColumnRead,
    DatasetColumnsResponse,
    DatasetErrorDetail,
    DatasetPreviewResponse,
    DatasetRead,
    DatasetUpdate,
    ValidationFindingRead,
)
from app.services import dataset_service
from app.services.dataset_service import DatasetServiceError

router = APIRouter(prefix="/datasets", tags=["datasets"])

settings = get_settings()


def _raise_service_error(exc: DatasetServiceError) -> None:
    detail = DatasetErrorDetail(
        code=exc.code,
        message=exc.message,
        findings=[
            ValidationFindingRead(
                severity=f.severity,
                code=f.code,
                message=f.message,
                row_number=f.row_number,
                column_name=f.column_name,
            )
            for f in exc.findings
        ],
    )
    raise HTTPException(status_code=exc.status_code, detail=detail.model_dump(mode="json"))


def _columns_response(columns: list[DatasetColumn]) -> DatasetColumnsResponse:
    mapped_fields = {c.mapped_business_field for c in columns if c.mapped_business_field}
    return DatasetColumnsResponse(
        columns=[DatasetColumnRead.model_validate(c) for c in columns],
        available_analyses=dataset_service.available_analyses(mapped_fields),
    )


@router.post("/upload", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    display_name: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetRead:
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit():
        if int(content_length) > settings.max_upload_size_bytes:
            _raise_service_error(
                DatasetServiceError(
                    413,
                    "FILE_TOO_LARGE",
                    f"File exceeds the maximum allowed size of "
                    f"{settings.max_upload_size_bytes} bytes.",
                )
            )

    try:
        dataset = await dataset_service.process_upload(db, current_user, file, display_name)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise  # unreachable, satisfies type checkers

    return DatasetRead.model_validate(dataset)


@router.get("", response_model=list[DatasetRead])
async def list_datasets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DatasetRead]:
    owner_filter = None if current_user.role == Role.ADMIN else current_user.id
    datasets = await dataset_crud.list_datasets(db, owner_user_id=owner_filter)
    return [DatasetRead.model_validate(d) for d in datasets]


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset(
    dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetRead:
    try:
        dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise
    return DatasetRead.model_validate(dataset)


@router.get("/{dataset_id}/preview", response_model=DatasetPreviewResponse)
async def get_dataset_preview(
    dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetPreviewResponse:
    try:
        dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    columns, rows = dataset_service.get_preview(dataset)
    return DatasetPreviewResponse(
        columns=columns,
        rows=rows,
        returned_row_count=len(rows),
        total_row_count=dataset.row_count,
    )


@router.get("/{dataset_id}/columns", response_model=DatasetColumnsResponse)
async def get_dataset_columns(
    dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetColumnsResponse:
    try:
        dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    columns = await dataset_crud.get_columns(db, dataset.id)
    return _columns_response(columns)


@router.patch("/{dataset_id}", response_model=DatasetRead)
async def update_dataset(
    dataset_id: uuid.UUID,
    payload: DatasetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetRead:
    try:
        dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
        dataset = await dataset_service.update_display_name(
            db, dataset, payload.display_name, current_user
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise
    return DatasetRead.model_validate(dataset)


@router.patch("/{dataset_id}/columns", response_model=DatasetColumnsResponse)
async def update_dataset_columns(
    dataset_id: uuid.UUID,
    payload: ColumnMappingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetColumnsResponse:
    try:
        dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
        columns = await dataset_service.update_column_mappings(
            db, dataset, payload.columns, current_user
        )
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise

    return _columns_response(columns)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
        await dataset_service.delete_dataset(db, dataset, current_user)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise


@router.post("/{dataset_id}/validate", response_model=DatasetRead)
async def validate_dataset(
    dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetRead:
    try:
        dataset = await dataset_service.get_owned_dataset_or_404(db, dataset_id, current_user)
        dataset = await dataset_service.revalidate_dataset(db, dataset, current_user)
    except DatasetServiceError as exc:
        _raise_service_error(exc)
        raise
    return DatasetRead.model_validate(dataset)
