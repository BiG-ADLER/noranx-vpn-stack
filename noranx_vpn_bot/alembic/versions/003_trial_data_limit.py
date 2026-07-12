"""subscription data_limit_bytes

Revision ID: 003
Revises: 002
Create Date: 2026-06-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("data_limit_bytes", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "data_limit_bytes")
