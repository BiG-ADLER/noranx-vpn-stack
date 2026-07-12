"""c2c review statuses and receipt dedup

Revision ID: 002
Revises: 001
Create Date: 2026-06-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'pending_review'")
    op.execute("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'rejected'")

    op.create_table(
        "c2c_receipt_dedup",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_c2c_receipt_dedup_receipt_sha256", "c2c_receipt_dedup", ["receipt_sha256"])
    op.create_index("ix_c2c_receipt_dedup_payment_id", "c2c_receipt_dedup", ["payment_id"])
    op.create_index("ix_payments_provider_status", "payments", ["provider", "status"])


def downgrade() -> None:
    op.drop_index("ix_payments_provider_status", table_name="payments")
    op.drop_index("ix_c2c_receipt_dedup_payment_id", table_name="c2c_receipt_dedup")
    op.drop_index("ix_c2c_receipt_dedup_receipt_sha256", table_name="c2c_receipt_dedup")
    op.drop_table("c2c_receipt_dedup")
