"""Subscription packages and user/merchant subscriptions

Revision ID: 011_subscription_packages
Revises: 010_merchant_profile_sync
Create Date: 2026-10-29 14:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_subscription_packages"
down_revision: Union[str, None] = "010_merchant_profile_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    user_cols = {c["name"] for c in insp.get_columns("users")} if "users" in tables else set()
    if "subscription_plan" not in user_cols:
        op.add_column("users", sa.Column("subscription_plan", sa.String(length=80), nullable=True))

    if "merchant_profiles" in tables:
        merch_cols = {c["name"] for c in insp.get_columns("merchant_profiles")}
        if "can_create_promotions" not in merch_cols:
            op.add_column(
                "merchant_profiles",
                sa.Column("can_create_promotions", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )
        if "has_active_subscription" not in merch_cols:
            op.add_column(
                "merchant_profiles",
                sa.Column(
                    "has_active_subscription",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )

    if "subscription_packages" not in tables:
        op.create_table(
            "subscription_packages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("audience", sa.String(length=20), nullable=False),
            sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
            sa.Column("billing_period", sa.String(length=20), nullable=False, server_default="MONTHLY"),
            sa.Column("duration_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
            sa.Column("features", sa.JSON(), nullable=True),
            sa.Column("grants", sa.JSON(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )
        op.create_index("ix_subscription_packages_id", "subscription_packages", ["id"])
        op.create_index("ix_subscription_packages_code", "subscription_packages", ["code"], unique=True)
        op.create_index("ix_subscription_packages_audience", "subscription_packages", ["audience"])
        op.create_index("ix_subscription_packages_is_active", "subscription_packages", ["is_active"])

    if "user_subscriptions" not in tables:
        op.create_table(
            "user_subscriptions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("subscription_code", sa.String(length=50), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("merchant_profile_id", sa.Integer(), nullable=True),
            sa.Column("package_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
            sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
            sa.Column("payment_reference", sa.String(length=255), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["merchant_profile_id"], ["merchant_profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["package_id"], ["subscription_packages.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("subscription_code"),
        )
        op.create_index("ix_user_subscriptions_id", "user_subscriptions", ["id"])
        op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
        op.create_index(
            "ix_user_subscriptions_merchant_profile_id",
            "user_subscriptions",
            ["merchant_profile_id"],
        )
        op.create_index("ix_user_subscriptions_package_id", "user_subscriptions", ["package_id"])
        op.create_index("ix_user_subscriptions_status", "user_subscriptions", ["status"])

    op.execute(
        """
        INSERT INTO subscription_packages
            (code, name, description, audience, price, currency, billing_period, duration_days,
             features, grants, is_active, sort_order, created_at, updated_at)
        SELECT 'USER_FREE', 'User Free', 'Browse merchants, favorites, and wallet cashback.',
               'USER', 0, 'INR', 'ONE_TIME', 3650, '[]', '{}', true, 0, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM subscription_packages WHERE code = 'USER_FREE')
        """
    )
    op.execute(
        """
        INSERT INTO subscription_packages
            (code, name, description, audience, price, currency, billing_period, duration_days,
             features, grants, is_active, sort_order, created_at, updated_at)
        SELECT 'USER_SELLER_500', 'Seller Plan ₹500', 'List products on Logo marketplace.',
               'USER', 500, 'INR', 'MONTHLY', 30, '[]',
               '{"can_sell_products": true, "is_subscriber": true, "subscription_plan": "500_SELLER"}',
               true, 1, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM subscription_packages WHERE code = 'USER_SELLER_500')
        """
    )
    op.execute(
        """
        INSERT INTO subscription_packages
            (code, name, description, audience, price, currency, billing_period, duration_days,
             features, grants, is_active, sort_order, created_at, updated_at)
        SELECT 'MERCHANT_PROMO_BASIC', 'Merchant Promotions', 'Create shop promotions and banners.',
               'MERCHANT', 999, 'INR', 'MONTHLY', 30, '[]', '{"can_create_promotions": true}',
               true, 0, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM subscription_packages WHERE code = 'MERCHANT_PROMO_BASIC')
        """
    )
    op.execute(
        """
        INSERT INTO subscription_packages
            (code, name, description, audience, price, currency, billing_period, duration_days,
             features, grants, is_active, sort_order, created_at, updated_at)
        SELECT 'MERCHANT_PREMIUM', 'Merchant Premium', 'Promotions plus premium discovery visibility.',
               'MERCHANT', 1999, 'INR', 'MONTHLY', 30, '[]',
               '{"can_create_promotions": true, "premium_listing": true}',
               true, 1, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM subscription_packages WHERE code = 'MERCHANT_PREMIUM')
        """
    )


def downgrade() -> None:
    op.drop_table("user_subscriptions")
    op.drop_table("subscription_packages")
    conn = op.get_bind()
    if "users" in sa.inspect(conn).get_table_names():
        cols = {c["name"] for c in sa.inspect(conn).get_columns("users")}
        if "subscription_plan" in cols:
            op.drop_column("users", "subscription_plan")
    if "merchant_profiles" in sa.inspect(conn).get_table_names():
        cols = {c["name"] for c in sa.inspect(conn).get_columns("merchant_profiles")}
        if "has_active_subscription" in cols:
            op.drop_column("merchant_profiles", "has_active_subscription")
