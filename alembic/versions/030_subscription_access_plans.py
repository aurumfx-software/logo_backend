"""Customer and merchant subscription access plans.

Revision ID: 030_subscription_access_plans
Revises: 029_shiprocket_columns
"""
import json
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030_subscription_access_plans"
down_revision: Union[str, None] = "029_shiprocket_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PACKAGES = [
    {
        "code": "USER_FREE",
        "name": "Customer Free ₹0",
        "description": "Browse the app. Product selling and sale cashback are not included.",
        "audience": "USER",
        "price": 0,
        "billing_period": "ONE_TIME",
        "duration_days": 3650,
        "features": ["Browse directory", "Browse marketplace"],
        "grants": {},
        "sort_order": 0,
    },
    {
        "code": "USER_SELLER_500",
        "name": "Customer Cashback Seller ₹499",
        "description": "Sell products and receive cashback on those sales.",
        "audience": "USER",
        "price": 499,
        "billing_period": "MONTHLY",
        "duration_days": 30,
        "features": ["Sell products", "Cashback on sales", "Seller dashboard"],
        "grants": {
            "can_sell_products": True,
            "cashback_on_sales": True,
            "is_subscriber": True,
            "subscription_plan": "499_SELLER",
        },
        "sort_order": 1,
    },
    {
        "code": "MERCHANT_PROMO_BASIC",
        "name": "Merchant Photos ₹999",
        "description": "Add photos on the merchant profile.",
        "audience": "MERCHANT",
        "price": 999,
        "billing_period": "MONTHLY",
        "duration_days": 30,
        "features": ["Profile photos"],
        "grants": {"can_add_photos": True},
        "sort_order": 0,
    },
    {
        "code": "MERCHANT_PREMIUM",
        "name": "Merchant Photos & Video ₹1999",
        "description": "Add photos and video on the merchant profile.",
        "audience": "MERCHANT",
        "price": 1999,
        "billing_period": "MONTHLY",
        "duration_days": 30,
        "features": ["Profile photos", "Profile video"],
        "grants": {"can_add_photos": True, "can_add_videos": True},
        "sort_order": 1,
    },
    {
        "code": "MERCHANT_SELL_2999",
        "name": "Merchant Seller ₹2999",
        "description": "Photos, video, and product selling.",
        "audience": "MERCHANT",
        "price": 2999,
        "billing_period": "MONTHLY",
        "duration_days": 30,
        "features": ["Profile photos", "Profile video", "Sell products"],
        "grants": {"can_add_photos": True, "can_add_videos": True, "can_sell_products": True},
        "sort_order": 2,
    },
    {
        "code": "MERCHANT_DETAIL_3999",
        "name": "Merchant Detail Ad ₹3999",
        "description": "Photos, video, product selling, and an advertisement on the merchant details page.",
        "audience": "MERCHANT",
        "price": 3999,
        "billing_period": "MONTHLY",
        "duration_days": 30,
        "features": ["Profile photos", "Profile video", "Sell products", "Details page advertisement"],
        "grants": {
            "can_add_photos": True,
            "can_add_videos": True,
            "can_sell_products": True,
            "can_add_detail_page_ad": True,
        },
        "sort_order": 3,
    },
    {
        "code": "MERCHANT_LANDING_4999",
        "name": "Merchant Landing Promotion ₹4999",
        "description": "Everything in the ₹3999 plan, plus a landing-page promotion. Landing ads stay pending until an admin approves them.",
        "audience": "MERCHANT",
        "price": 4999,
        "billing_period": "MONTHLY",
        "duration_days": 30,
        "features": [
            "Profile photos",
            "Profile video",
            "Sell products",
            "Details page advertisement",
            "Landing page promotion",
        ],
        "grants": {
            "can_add_photos": True,
            "can_add_videos": True,
            "can_sell_products": True,
            "can_add_detail_page_ad": True,
            "can_promote_landing": True,
        },
        "sort_order": 4,
    },
]

LEGACY_GRANTS = {
    "USER_SELLER_500": [
        {"can_sell_products": True, "is_subscriber": True, "subscription_plan": "500_SELLER"},
    ],
    "MERCHANT_PROMO_BASIC": [
        {"can_create_promotions": True},
    ],
    "MERCHANT_PREMIUM": [
        {"can_create_promotions": True, "premium_listing": True},
    ],
}


def _signature(grants) -> dict:
    if isinstance(grants, str):
        try:
            grants = json.loads(grants)
        except json.JSONDecodeError:
            grants = {}
    signature = {}
    for key, value in (grants or {}).items():
        if not value:
            continue
        signature[key] = value if key == "subscription_plan" else True
    return signature


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "subscription_packages" not in inspector.get_table_names():
        return

    packages = sa.table(
        "subscription_packages",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("audience", sa.String),
        sa.column("price", sa.Numeric),
        sa.column("currency", sa.String),
        sa.column("billing_period", sa.String),
        sa.column("duration_days", sa.Integer),
        sa.column("features", sa.JSON),
        sa.column("grants", sa.JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    rows = conn.execute(sa.select(packages.c.code, packages.c.price, packages.c.grants, packages.c.name)).mappings().all()
    existing = {row["code"]: row for row in rows}
    now = datetime.now(timezone.utc)

    for row in PACKAGES:
        current = existing.get(row["code"])
        if current is None:
            conn.execute(
                packages.insert().values(
                    code=row["code"],
                    name=row["name"],
                    description=row["description"],
                    audience=row["audience"],
                    price=row["price"],
                    currency="INR",
                    billing_period=row["billing_period"],
                    duration_days=row["duration_days"],
                    features=row["features"],
                    grants=row["grants"],
                    is_active=True,
                    sort_order=row["sort_order"],
                    created_at=now,
                    updated_at=now,
                )
            )
            continue
        price = current["price"]
        still_legacy = _signature(current["grants"]) in LEGACY_GRANTS.get(row["code"], []) or (
            row["code"] == "USER_SELLER_500" and price is not None and float(price) == 500.0
        ) or (row["code"] == "USER_FREE" and (current["name"] or "") == "User Free")
        if still_legacy:
            conn.execute(
                packages.update()
                .where(packages.c.code == row["code"])
                .values(
                    name=row["name"],
                    description=row["description"],
                    price=row["price"],
                    billing_period=row["billing_period"],
                    duration_days=row["duration_days"],
                    features=row["features"],
                    grants=row["grants"],
                    sort_order=row["sort_order"],
                    is_active=True,
                    updated_at=now,
                )
            )


def downgrade() -> None:
    pass
