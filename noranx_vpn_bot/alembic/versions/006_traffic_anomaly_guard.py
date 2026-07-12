"""traffic anomaly guard schema

Revision ID: 006
Revises: 005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    trafficanomalystatus = postgresql.ENUM(
        "watch",
        "disabled",
        "false_positive",
        "resolved",
        name="trafficanomalystatus",
    )
    trafficanomalystatus.create(op.get_bind(), checkfirst=True)
    trafficanomalystatus_col = postgresql.ENUM(
        "watch",
        "disabled",
        "false_positive",
        "resolved",
        name="trafficanomalystatus",
        create_type=False,
    )

    op.create_table(
        "traffic_usage_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("marzban_username", sa.String(length=32), nullable=False),
        sa.Column("used_traffic_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_traffic_usage_snapshots_subscription_id",
        "traffic_usage_snapshots",
        ["subscription_id"],
    )
    op.create_index(
        "ix_traffic_usage_snapshots_marzban_username",
        "traffic_usage_snapshots",
        ["marzban_username"],
    )
    op.create_index("ix_traffic_usage_snapshots_checked_at", "traffic_usage_snapshots", ["checked_at"])
    op.create_index(
        "ix_traffic_usage_snapshots_user_checked_desc",
        "traffic_usage_snapshots",
        [sa.text("marzban_username"), sa.text("checked_at DESC")],
    )
    op.create_index(
        "ix_traffic_usage_snapshots_sub_checked_desc",
        "traffic_usage_snapshots",
        [sa.text("subscription_id"), sa.text("checked_at DESC")],
    )

    op.create_table(
        "traffic_anomaly_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("marzban_username", sa.String(length=32), nullable=False),
        sa.Column("status", trafficanomalystatus_col, nullable=False),
        sa.Column("score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("delta_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("delta_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rate_mbps", sa.Float(), server_default="0", nullable=False),
        sa.Column("device_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("threshold_floor_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("baseline_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.String(length=64), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_traffic_anomaly_events_subscription_id",
        "traffic_anomaly_events",
        ["subscription_id"],
    )
    op.create_index(
        "ix_traffic_anomaly_events_marzban_username",
        "traffic_anomaly_events",
        ["marzban_username"],
    )
    op.create_index(
        "ix_traffic_anomaly_events_status",
        "traffic_anomaly_events",
        ["status"],
    )
    op.create_index(
        "ix_traffic_anomaly_events_created_at",
        "traffic_anomaly_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_traffic_anomaly_events_created_at", table_name="traffic_anomaly_events")
    op.drop_index("ix_traffic_anomaly_events_status", table_name="traffic_anomaly_events")
    op.drop_index("ix_traffic_anomaly_events_marzban_username", table_name="traffic_anomaly_events")
    op.drop_index("ix_traffic_anomaly_events_subscription_id", table_name="traffic_anomaly_events")
    op.drop_table("traffic_anomaly_events")

    op.drop_index(
        "ix_traffic_usage_snapshots_sub_checked_desc",
        table_name="traffic_usage_snapshots",
    )
    op.drop_index(
        "ix_traffic_usage_snapshots_user_checked_desc",
        table_name="traffic_usage_snapshots",
    )
    op.drop_index("ix_traffic_usage_snapshots_checked_at", table_name="traffic_usage_snapshots")
    op.drop_index("ix_traffic_usage_snapshots_marzban_username", table_name="traffic_usage_snapshots")
    op.drop_index("ix_traffic_usage_snapshots_subscription_id", table_name="traffic_usage_snapshots")
    op.drop_table("traffic_usage_snapshots")
    op.execute("DROP TYPE IF EXISTS trafficanomalystatus")
