"""admin cms messaging tables

Revision ID: 004
Revises: 003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLATFORM_SEED = [
    ("android", "Android", 0),
    ("ios", "iOS", 1),
    ("desktop", "Windows / Linux", 2),
    ("macos", "macOS", 3),
]

APP_SEED = {
    "v2rayng": ("V2RayNG", "android", "", 0),
    "v2rayn": ("v2rayN", "desktop", "", 0),
    "v2box": ("V2Box", "android", "", 1),
    "happ": ("Happ", "android", "", 2),
    "v2raytun": ("v2RayTun", "android", "", 3),
}

STEP_SEED = {
    "v2rayng": [
        "از منوی ربات «سرویس‌های من» لینک اشتراک را کپی کنید.",
        "V2RayNG را باز کنید → منو (+) → Import config from Clipboard.",
        "یا QR را از ربات اسکن کنید (دکمه QR).",
        "روی کانفیگ بزنید و اتصال را فعال کنید.",
    ],
    "v2rayn": [
        "لینک اشتراک را از ربات کپی کنید.",
        "v2rayN → Subscription group → Add subscription.",
        "لینک را Paste کنید و Update subscription بزنید.",
        "یک سرور انتخاب کنید و System proxy یا TUN را فعال کنید.",
    ],
    "v2box": [
        "لینک اشتراک را از ربات دریافت کنید.",
        "V2Box → Add → Import from URL.",
        "لینک را وارد کنید و Subscribe/Update بزنید.",
        "پروفایل را انتخاب و Connect کنید.",
    ],
    "happ": [
        "لینک اشتراک را از ربات کپی کنید.",
        "Happ → افزودن اشتراک → از لینک.",
        "لینک را Paste و ذخیره کنید.",
        "اشتراک را بروزرسانی و اتصال را برقرار کنید.",
    ],
    "v2raytun": [
        "لینک اشتراک یا QR را از ربات بگیرید.",
        "v2RayTun → + → Import from clipboard یا Scan QR.",
        "پروفایل را انتخاب و اتصال را روشن کنید.",
    ],
}

EXTRA_TIPS = {
    "v2rayn": (
        "برای محدودیت دستگاه در v2rayN: برای هر دستگاه User-Agent اختصاصی تنظیم کنید "
        "و «بروزرسانی اشتراک» را بزنید."
    ),
}

# platform -> app slugs (multi-platform apps duplicated per platform row)
PLATFORM_APPS = {
    "android": ["v2rayng", "v2box", "v2raytun", "happ"],
    "ios": ["v2box", "v2raytun", "happ"],
    "desktop": ["v2rayn"],
    "macos": ["v2box"],
}


def upgrade() -> None:
    op.add_column("plans", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))

    op.create_table(
        "guide_platforms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(32), unique=True, nullable=False),
        sa.Column("title_fa", sa.String(128), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_table(
        "guide_apps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform_id", sa.Integer(), sa.ForeignKey("guide_platforms.id"), nullable=False),
        sa.Column("slug", sa.String(32), nullable=False),
        sa.Column("title_fa", sa.String(128), nullable=False),
        sa.Column("download_url", sa.String(512), server_default="", nullable=False),
        sa.Column("extra_tip", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.UniqueConstraint("platform_id", "slug", name="uq_guide_app_platform_slug"),
    )
    op.create_table(
        "guide_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("guide_apps.id"), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("body_fa", sa.Text(), nullable=False),
        sa.UniqueConstraint("app_id", "step_no", name="uq_guide_step_app_no"),
    )
    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedup_key", sa.String(128), index=True, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    conn = op.get_bind()
    platform_ids: dict[str, int] = {}
    for slug, title, sort_order in PLATFORM_SEED:
        r = conn.execute(
            sa.text(
                "INSERT INTO guide_platforms (slug, title_fa, sort_order, is_active) "
                "VALUES (:slug, :title, :sort, true) RETURNING id"
            ),
            {"slug": slug, "title": title, "sort": sort_order},
        )
        platform_ids[slug] = r.scalar_one()

    for platform_slug, app_slugs in PLATFORM_APPS.items():
        pid = platform_ids[platform_slug]
        for idx, app_slug in enumerate(app_slugs):
            title, _, _, _ = APP_SEED[app_slug]
            r = conn.execute(
                sa.text(
                    "INSERT INTO guide_apps (platform_id, slug, title_fa, download_url, "
                    "extra_tip, sort_order, is_active) "
                    "VALUES (:pid, :slug, :title, '', :tip, :sort, true) RETURNING id"
                ),
                {
                    "pid": pid,
                    "slug": app_slug,
                    "title": title,
                    "tip": EXTRA_TIPS.get(app_slug),
                    "sort": idx,
                },
            )
            app_id = r.scalar_one()
            for step_no, body in enumerate(STEP_SEED.get(app_slug, []), 1):
                conn.execute(
                    sa.text(
                        "INSERT INTO guide_steps (app_id, step_no, body_fa) "
                        "VALUES (:aid, :no, :body)"
                    ),
                    {"aid": app_id, "no": step_no, "body": body},
                )


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_table("guide_steps")
    op.drop_table("guide_apps")
    op.drop_table("guide_platforms")
    op.drop_column("plans", "sort_order")
