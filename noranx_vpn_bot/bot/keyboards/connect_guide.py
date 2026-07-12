from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services import guides as guide_svc
from bot.services.connect_guide import APPS, PLATFORM_APPS


def guide_root_kb() -> InlineKeyboardMarkup:
    """Static fallback for tests; runtime uses guide_root_kb_async."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Android", callback_data="guide:platform:android"),
                InlineKeyboardButton(text="🍎 iOS", callback_data="guide:platform:ios"),
            ],
            [
                InlineKeyboardButton(text="🖥 Windows/Linux", callback_data="guide:platform:desktop"),
                InlineKeyboardButton(text="💻 macOS", callback_data="guide:platform:macos"),
            ],
            [InlineKeyboardButton(text="« منو", callback_data="menu:main")],
        ]
    )


def guide_platform_kb(platform: str) -> InlineKeyboardMarkup:
    app_ids = PLATFORM_APPS.get(platform, [])
    rows = [
        [InlineKeyboardButton(text=APPS[aid].name, callback_data=f"guide:app:{aid}:{platform}")]
        for aid in app_ids
        if aid in APPS
    ]
    rows.append([InlineKeyboardButton(text="« راهنما", callback_data="menu:guide")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def guide_root_kb_async(session: AsyncSession) -> InlineKeyboardMarkup:
    platforms = await guide_svc.list_platforms(session)
    if platforms:
        rows = []
        row = []
        for p in platforms:
            row.append(
                InlineKeyboardButton(text=p.title_fa, callback_data=f"guide:platform:{p.slug}")
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton(text="« منو", callback_data="menu:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Android", callback_data="guide:platform:android"),
                InlineKeyboardButton(text="🍎 iOS", callback_data="guide:platform:ios"),
            ],
            [
                InlineKeyboardButton(text="🖥 Windows/Linux", callback_data="guide:platform:desktop"),
                InlineKeyboardButton(text="💻 macOS", callback_data="guide:platform:macos"),
            ],
            [InlineKeyboardButton(text="« منو", callback_data="menu:main")],
        ]
    )


async def guide_platform_kb_async(session: AsyncSession, platform_slug: str) -> InlineKeyboardMarkup:
    platform = await guide_svc.get_platform_by_slug(session, platform_slug)
    if platform:
        apps = await guide_svc.list_apps_for_platform(session, platform.id)
        rows = [
            [InlineKeyboardButton(text=a.title_fa, callback_data=f"guide:app:{a.slug}:{platform_slug}")]
            for a in apps
        ]
        rows.append([InlineKeyboardButton(text="« راهنما", callback_data="menu:guide")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    app_ids = PLATFORM_APPS.get(platform_slug, [])
    rows = [
        [InlineKeyboardButton(text=APPS[aid].name, callback_data=f"guide:app:{aid}:{platform_slug}")]
        for aid in app_ids
        if aid in APPS
    ]
    rows.append([InlineKeyboardButton(text="« راهنما", callback_data="menu:guide")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def guide_app_kb(app_slug: str, platform_slug: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« بازگشت", callback_data=f"guide:platform:{platform_slug}")],
            [
                InlineKeyboardButton(text="📦 سرویس‌های من", callback_data="menu:accounts"),
                InlineKeyboardButton(text="🛒 خرید", callback_data="menu:shop"),
            ],
            [InlineKeyboardButton(text="« منو", callback_data="menu:main")],
        ]
    )


def guide_app_kb_with_download(app_slug: str, platform_slug: str, download_url: str) -> InlineKeyboardMarkup:
    rows = []
    if download_url:
        rows.append([InlineKeyboardButton(text="⬇️ دانلود اپ", url=download_url)])
    rows.extend(guide_app_kb(app_slug, platform_slug).inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)
