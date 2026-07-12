"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("referral_code", sa.String(16), nullable=False, unique=True),
        sa.Column("referred_by_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=True),
        sa.Column("trial_used", sa.Boolean(), server_default="false"),
        sa.Column("wallet_balance_toman", sa.Integer(), server_default="0"),
        sa.Column("is_banned", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_telegram_users_telegram_id", "telegram_users", ["telegram_id"])

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(32), nullable=False, unique=True),
        sa.Column("name_fa", sa.String(128), nullable=False),
        sa.Column("device_count", sa.Integer(), nullable=False),
        sa.Column("price_toman", sa.Integer(), nullable=False),
        sa.Column("duration_days", sa.Integer(), server_default="30"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )

    op.create_table(
        "recharge_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount_toman", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )

    op.create_table(
        "discount_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("discount_type", sa.Enum("percent", "fixed", name="discounttype"), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default="1"),
        sa.Column("used_count", sa.Integer(), server_default="0"),
        sa.Column("per_user_limit", sa.Integer(), server_default="1"),
        sa.Column("min_order_toman", sa.Integer(), server_default="0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applicable_plan_slugs", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_for_user_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=True),
    )

    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )

    op.create_table(
        "system_state",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("marzban_username", sa.String(32), nullable=False, unique=True),
        sa.Column("subscription_url", sa.Text(), nullable=True),
        sa.Column("device_limit", sa.Integer(), server_default="1"),
        sa.Column("ip_limit", sa.Integer(), server_default="1"),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("is_trial", sa.Boolean(), server_default="false"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "expired",
                "disabled",
                "limited",
                "provisioning_failed",
                name="subscriptionstatus",
            ),
            server_default="active",
        ),
        sa.Column("used_traffic_bytes", sa.BigInteger(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1"),
        sa.Column("unit_price_toman", sa.Integer(), nullable=False),
        sa.Column("discount_id", sa.Integer(), sa.ForeignKey("discount_codes.id"), nullable=True),
        sa.Column("total_toman", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "paid",
                "provisioning",
                "completed",
                "failed",
                "refunded",
                name="orderstatus",
            ),
            server_default="pending",
        ),
        sa.Column("is_renewal", sa.Boolean(), server_default="false"),
        sa.Column("renew_subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("success", sa.Boolean(), server_default="false"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("recharge_package_id", sa.Integer(), sa.ForeignKey("recharge_packages.id"), nullable=True),
        sa.Column(
            "provider",
            sa.Enum("wallet", "nowpayments", "c2c", name="paymentprovider"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("amount_toman", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "completed", "failed", name="paymentstatus"),
            server_default="pending",
        ),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("external_id", "provider", name="uq_payment_external"),
    )

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("amount_toman", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column(
            "tx_type",
            sa.Enum("deposit", "purchase", "refund", "admin_adjust", name="wallettxtype"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("referee_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_discount_id", sa.Integer(), sa.ForeignKey("discount_codes.id"), nullable=True),
        sa.UniqueConstraint("referee_id", name="uq_referral_referee"),
    )

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "answered", "closed", name="ticketstatus"),
            server_default="open",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=False),
        sa.Column("from_admin", sa.Boolean(), server_default="false"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "provisioning_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("service", sa.String(32), nullable=False),
        sa.Column("request_summary", sa.Text(), nullable=True),
        sa.Column("response_summary", sa.Text(), nullable=True),
        sa.Column("ok", sa.Boolean(), server_default="false"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "admin_audit_log",
        "provisioning_logs",
        "support_messages",
        "support_tickets",
        "referrals",
        "wallet_transactions",
        "payments",
        "order_items",
        "orders",
        "subscriptions",
        "system_state",
        "settings",
        "discount_codes",
        "recharge_packages",
        "plans",
        "telegram_users",
    ):
        op.drop_table(table)
