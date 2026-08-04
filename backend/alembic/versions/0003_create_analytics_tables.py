"""create analytics tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

analytics_job_status_enum = sa.Enum("running", "completed", "failed", name="analytics_job_status")
kpi_name_enum = sa.Enum(
    "revenue",
    "gross_profit",
    "gross_margin",
    "average_selling_price",
    "average_order_value",
    "inventory_value",
    "inventory_turnover",
    "sell_through_rate",
    "return_rate",
    "return_cost",
    "units_sold",
    "units_returned",
    "stockouts",
    "overstock_count",
    "low_inventory_count",
    name="kpi_name",
)

# dataset_finding_severity already exists (created by migration 0002 for
# dataset_validation_findings.severity); DataQualityFinding.severity
# reuses that same Postgres enum type rather than creating a duplicate,
# so this reference must never call .create() - only use it to type a
# column, with create_type=False so op.create_table doesn't try to.
dataset_finding_severity_enum = sa.Enum(
    "info", "warning", "error", name="dataset_finding_severity", create_type=False
)

NEW_ENUMS = [analytics_job_status_enum, kpi_name_enum]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "analytics_jobs",
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
        sa.Column("status", analytics_job_status_enum, nullable=False, server_default="running"),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analytics_jobs_dataset_id", "analytics_jobs", ["dataset_id"])

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("analytics_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("mapped_field_count", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_analytics_snapshots_dataset_id", "analytics_snapshots", ["dataset_id"])
    op.create_index("ix_analytics_snapshots_job_id", "analytics_snapshots", ["job_id"])

    op.create_table(
        "kpi_results",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("analytics_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kpi_name", kpi_name_enum, nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_kpi_results_snapshot_id", "kpi_results", ["snapshot_id"])

    op.create_table(
        "data_quality_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("analytics_snapshots.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("completeness_score", sa.Float(), nullable=False),
        sa.Column("validity_score", sa.Float(), nullable=False),
        sa.Column("consistency_score", sa.Float(), nullable=False),
        sa.Column("uniqueness_score", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_data_quality_reports_snapshot_id", "data_quality_reports", ["snapshot_id"])

    op.create_table(
        "data_quality_findings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey("data_quality_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", dataset_finding_severity_enum, nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("recommendation", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_data_quality_findings_report_id", "data_quality_findings", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_data_quality_findings_report_id", table_name="data_quality_findings")
    op.drop_table("data_quality_findings")

    op.drop_index("ix_data_quality_reports_snapshot_id", table_name="data_quality_reports")
    op.drop_table("data_quality_reports")

    op.drop_index("ix_kpi_results_snapshot_id", table_name="kpi_results")
    op.drop_table("kpi_results")

    op.drop_index("ix_analytics_snapshots_job_id", table_name="analytics_snapshots")
    op.drop_index("ix_analytics_snapshots_dataset_id", table_name="analytics_snapshots")
    op.drop_table("analytics_snapshots")

    op.drop_index("ix_analytics_jobs_dataset_id", table_name="analytics_jobs")
    op.drop_table("analytics_jobs")

    bind = op.get_bind()
    for enum_type in reversed(NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
