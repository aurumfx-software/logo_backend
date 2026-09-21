"""Add merchant approval columns and create notifications and activity_logs tables

Revision ID: 005_merchant_approval
Revises: 004_logo_platform_features
Create Date: 2026-09-19 15:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic (max 32 chars in alembic_version table)
revision: str = "005_merchant_approval"
down_revision: Union[str, None] = "004_logo_platform_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()

    # 1. Add missing approval columns to merchant_profiles
    existing_cols = [c["name"] for c in insp.get_columns("merchant_profiles")]

    if "approval_status" not in existing_cols:
        op.add_column(
            "merchant_profiles",
            sa.Column("approval_status", sa.String(length=50), nullable=False, server_default="PENDING"),
        )
        op.create_index(
            op.f("ix_merchant_profiles_approval_status"),
            "merchant_profiles",
            ["approval_status"],
            unique=False,
        )
    if "rejection_reason" not in existing_cols:
        op.add_column(
            "merchant_profiles",
            sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        )
    if "approved_by_id" not in existing_cols:
        op.add_column(
            "merchant_profiles",
            sa.Column("approved_by_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_merchant_profiles_approved_by_id_users",
            "merchant_profiles",
            "users",
            ["approved_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "approved_at" not in existing_cols:
        op.add_column(
            "merchant_profiles",
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "is_active" not in existing_cols:
        op.add_column(
            "merchant_profiles",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    # 2. Create notifications table if not exists
    if "notifications" not in existing_tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("type", sa.String(length=50), nullable=False, server_default="INFO"),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_notifications_id"), "notifications", ["id"], unique=False)
        op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
        op.create_index(op.f("ix_notifications_type"), "notifications", ["type"], unique=False)
        op.create_index(op.f("ix_notifications_is_read"), "notifications", ["is_read"], unique=False)

    # 3. Create activity_logs table if not exists
    if "activity_logs" not in existing_tables:
        op.create_table(
            "activity_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_activity_logs_id"), "activity_logs", ["id"], unique=False)
        op.create_index(op.f("ix_activity_logs_user_id"), "activity_logs", ["user_id"], unique=False)
        op.create_index(op.f("ix_activity_logs_action"), "activity_logs", ["action"], unique=False)
        op.create_index(op.f("ix_activity_logs_entity_type"), "activity_logs", ["entity_type"], unique=False)
        op.create_index(op.f("ix_activity_logs_entity_id"), "activity_logs", ["entity_id"], unique=False)
        op.create_index(op.f("ix_activity_logs_created_at"), "activity_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_activity_logs_created_at"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_entity_id"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_entity_type"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_action"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_user_id"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_id"), table_name="activity_logs")
    op.drop_table("activity_logs")

    op.drop_index(op.f("ix_notifications_is_read"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_type"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_id"), table_name="notifications")
    op.drop_table("notifications")

    op.drop_index(op.f("ix_merchant_profiles_approval_status"), table_name="merchant_profiles")
    op.drop_constraint("fk_merchant_profiles_approved_by_id_users", "merchant_profiles", type_="foreignkey")
    op.drop_column("merchant_profiles", "is_active")
    op.drop_column("merchant_profiles", "approved_at")
    op.drop_column("merchant_profiles", "approved_by_id")
    op.drop_column("merchant_profiles", "rejection_reason")
    op.drop_column("merchant_profiles", "approval_status")
