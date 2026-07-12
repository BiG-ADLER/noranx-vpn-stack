"""ticket crm fields and notes

Revision ID: 005
Revises: 004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE ticketstatus ADD VALUE IF NOT EXISTS 'in_progress'")
    op.execute("ALTER TYPE ticketstatus ADD VALUE IF NOT EXISTS 'waiting_user'")
    op.execute("ALTER TYPE ticketstatus ADD VALUE IF NOT EXISTS 'resolved'")

    ticketpriority = sa.Enum(
        "low",
        "normal",
        "high",
        "urgent",
        name="ticketpriority",
    )
    ticketpriority.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "support_tickets",
        sa.Column("title", sa.String(length=255), server_default="درخواست پشتیبانی", nullable=False),
    )
    op.alter_column("support_tickets", "category", existing_type=sa.String(length=64), nullable=False)
    op.add_column(
        "support_tickets",
        sa.Column("priority", ticketpriority, server_default="normal", nullable=False),
    )
    op.add_column("support_tickets", sa.Column("assignee_admin_id", sa.BigInteger(), nullable=True))
    op.add_column("support_tickets", sa.Column("tags_json", sa.Text(), nullable=True))
    op.add_column("support_tickets", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("support_tickets", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "support_tickets",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "support_ticket_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_ticket_notes_ticket_id", "support_ticket_notes", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_support_ticket_notes_ticket_id", table_name="support_ticket_notes")
    op.drop_table("support_ticket_notes")

    op.drop_column("support_tickets", "updated_at")
    op.drop_column("support_tickets", "closed_at")
    op.drop_column("support_tickets", "due_at")
    op.drop_column("support_tickets", "tags_json")
    op.drop_column("support_tickets", "assignee_admin_id")
    op.drop_column("support_tickets", "priority")
    op.drop_column("support_tickets", "title")

    op.execute("DROP TYPE IF EXISTS ticketpriority")
