"""create dataset ingestion tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

dataset_status_enum = sa.Enum(
    "uploaded", "validating", "ready", "failed", "deleted", name="dataset_status"
)
dataset_file_type_enum = sa.Enum("csv", "xlsx", name="dataset_file_type")
dataset_column_type_enum = sa.Enum(
    "string",
    "integer",
    "float",
    "boolean",
    "date",
    "datetime",
    "unknown",
    name="dataset_column_type",
)
dataset_business_field_enum = sa.Enum(
    "product_id",
    "sku",
    "upc",
    "product_name",
    "category",
    "brand",
    "supplier",
    "unit_cost",
    "retail_price",
    "sale_price",
    "quantity_available",
    "quantity_sold",
    "quantity_returned",
    "order_id",
    "order_date",
    "return_date",
    "customer_id",
    "region",
    "channel",
    "status",
    name="dataset_business_field",
)
dataset_upload_status_enum = sa.Enum("received", "stored", "failed", name="dataset_upload_status")
dataset_validation_run_status_enum = sa.Enum(
    "running", "passed", "failed", name="dataset_validation_run_status"
)
dataset_finding_severity_enum = sa.Enum("info", "warning", "error", name="dataset_finding_severity")
dataset_audit_event_type_enum = sa.Enum(
    "uploaded",
    "validation_started",
    "validation_passed",
    "validation_failed",
    "deleted",
    "columns_mapped",
    "display_name_updated",
    name="dataset_audit_event_type",
)

ALL_ENUMS = [
    dataset_status_enum,
    dataset_file_type_enum,
    dataset_column_type_enum,
    dataset_business_field_enum,
    dataset_upload_status_enum,
    dataset_validation_run_status_enum,
    dataset_finding_severity_enum,
    dataset_audit_event_type_enum,
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", dataset_file_type_enum, nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("status", dataset_status_enum, nullable=False, server_default="uploaded"),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("normalized_storage_path", sa.String(length=512), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_datasets_owner_user_id", "datasets", ["owner_user_id"])

    op.create_table(
        "dataset_columns",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "inferred_type", dataset_column_type_enum, nullable=False, server_default="unknown"
        ),
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sample_values", sa.JSON(), nullable=False),
        sa.Column("mapped_business_field", dataset_business_field_enum, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_dataset_columns_dataset_id", "dataset_columns", ["dataset_id"])

    op.create_table(
        "dataset_uploads",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_type", dataset_file_type_enum, nullable=False),
        sa.Column(
            "upload_status",
            dataset_upload_status_enum,
            nullable=False,
            server_default="received",
        ),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_dataset_uploads_dataset_id", "dataset_uploads", ["dataset_id"])

    op.create_table(
        "dataset_validation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "triggered_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            dataset_validation_run_status_enum,
            nullable=False,
            server_default="running",
        ),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(length=1000), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_dataset_validation_runs_dataset_id", "dataset_validation_runs", ["dataset_id"]
    )

    op.create_table(
        "dataset_validation_findings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "validation_run_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_validation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", dataset_finding_severity_enum, nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_dataset_validation_findings_validation_run_id",
        "dataset_validation_findings",
        ["validation_run_id"],
    )

    op.create_table(
        "dataset_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("event_type", dataset_audit_event_type_enum, nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_dataset_audit_events_dataset_id", "dataset_audit_events", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_dataset_audit_events_dataset_id", table_name="dataset_audit_events")
    op.drop_table("dataset_audit_events")

    op.drop_index(
        "ix_dataset_validation_findings_validation_run_id",
        table_name="dataset_validation_findings",
    )
    op.drop_table("dataset_validation_findings")

    op.drop_index("ix_dataset_validation_runs_dataset_id", table_name="dataset_validation_runs")
    op.drop_table("dataset_validation_runs")

    op.drop_index("ix_dataset_uploads_dataset_id", table_name="dataset_uploads")
    op.drop_table("dataset_uploads")

    op.drop_index("ix_dataset_columns_dataset_id", table_name="dataset_columns")
    op.drop_table("dataset_columns")

    op.drop_index("ix_datasets_owner_user_id", table_name="datasets")
    op.drop_table("datasets")

    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
