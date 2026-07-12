from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, LinkPreviewOptions

from bot.config import Settings, get_settings
from bot.services.marzban import MarzbanService
from bot.utils.qr import make_qr_png_bytes
from bot.utils.subscription_url import normalize_subscription_url

_PROTOCOL_LABELS = {
    "vless": "VLESS",
    "trojan": "Trojan",
    "vmess": "VMess",
    "ss": "Shadowsocks",
    "shadowsocks": "Shadowsocks",
}

_NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _protocol_label(link: str) -> str:
    proto = link.split("://", 1)[0].lower()
    return _PROTOCOL_LABELS.get(proto, proto.upper())


def format_manual_configs_message(links: list[str]) -> str:
    if not links:
        return ""
    lines = ["📋 <b>کانفیگ‌های دستی</b> (VLESS / Trojan / VMess / Shadowsocks):\n"]
    for link in links:
        label = _protocol_label(link)
        lines.append(f"▫️ <b>{label}</b>\n<code>{link}</code>\n")
    return "\n".join(lines)


async def _resolve_links(
    marzban: MarzbanService, username: str, links: list[str] | None
) -> list[str]:
    if links:
        return links
    user = await marzban.get_user(username)
    return list(user.links) if user and user.links else []


async def send_subscription_details(
    bot: Bot,
    chat_id: int,
    *,
    marzban_username: str,
    subscription_url: str | None,
    device_limit: int | None = None,
    account_index: int | None = None,
    header: str | None = None,
    proxy_links: list[str] | None = None,
    marzban: MarzbanService | None = None,
    settings: Settings | None = None,
    qr_caption: str = "QR اشتراک",
) -> None:
    settings = settings or get_settings()
    marzban = marzban or MarzbanService(settings)
    sub_url = normalize_subscription_url(subscription_url)

    if header:
        try:
            await bot.send_message(
                chat_id, header, link_preview_options=_NO_LINK_PREVIEW
            )
        except Exception:
            pass

    lines: list[str] = []
    if account_index is not None:
        lines.append(f"📦 حساب {account_index}")
    lines.append(f"👤 {marzban_username}")
    if device_limit is not None:
        lines.append(f"📱 ظرفیت: {device_limit} دستگاه")
        if device_limit == 1:
            lines.append(
                "💡 لینک اشتراک را فقط در اپ VPN (مثلاً v2rayNG) وارد کنید — "
                "باز کردن لینک در مرورگر یا تلگرام ظرفیت دستگاه را مصرف می‌کند."
            )
    if sub_url:
        lines.append("🔗 لینک اشتراک در فایل زیر و QR ارسال شده است.")

    if lines:
        try:
            await bot.send_message(
                chat_id,
                "\n".join(lines),
                link_preview_options=_NO_LINK_PREVIEW,
            )
        except Exception:
            pass

    if sub_url:
        try:
            qr = make_qr_png_bytes(sub_url)
            await bot.send_photo(
                chat_id,
                BufferedInputFile(qr, filename="qr.png"),
                caption=qr_caption,
            )
        except Exception:
            pass
        try:
            await bot.send_document(
                chat_id,
                BufferedInputFile(
                    sub_url.encode("utf-8"),
                    filename=f"{marzban_username}_subscription.txt",
                ),
                caption="لینک اشتراک — در اپ VPN import کنید",
            )
        except Exception:
            pass

    links = await _resolve_links(marzban, marzban_username, proxy_links)
    manual_text = format_manual_configs_message(links)
    if manual_text:
        try:
            await bot.send_message(
                chat_id,
                manual_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=_NO_LINK_PREVIEW,
            )
        except Exception:
            pass
