"""custom username on orders + referral wallet setting seed

Revision ID: 007
Revises: 006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("preferred_username", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_orders_preferred_username",
        "orders",
        ["preferred_username"],
        unique=False,
    )
    op.execute(
        sa.text(
            "INSERT INTO settings (key, value) VALUES ('referral_wallet_reward_toman', '10000') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_orders_preferred_username", table_name="orders")
    op.drop_column("orders", "preferred_username")
    op.execute(sa.text("DELETE FROM settings WHERE key = 'referral_wallet_reward_toman'"))
