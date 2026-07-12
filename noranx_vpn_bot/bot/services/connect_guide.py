"""Static Persian connect-guide content."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideApp:
    id: str
    name: str
    platforms: str
    steps: list[str]
    extra_tip: str = ""


DEVICE_LIMIT_TIP = (
    "برای محدودیت دستگاه در v2rayN: برای هر دستگاه User-Agent اختصاصی تنظیم کنید "
    "و «بروزرسانی اشتراک» را بزنید."
)

APPS: dict[str, GuideApp] = {
    "v2rayng": GuideApp(
        id="v2rayng",
        name="V2RayNG",
        platforms="Android",
        steps=[
            "از منوی ربات «سرویس‌های من» لینک اشتراک را کپی کنید.",
            "V2RayNG را باز کنید → منو (+) → Import config from Clipboard.",
            "یا QR را از ربات اسکن کنید (دکمه QR).",
            "روی کانفیگ بزنید و اتصال را فعال کنید.",
        ],
    ),
    "v2rayn": GuideApp(
        id="v2rayn",
        name="v2rayN",
        platforms="Windows / Linux",
        steps=[
            "لینک اشتراک را از ربات کپی کنید.",
            "v2rayN → Subscription group → Add subscription.",
            "لینک را Paste کنید و Update subscription بزنید.",
            "یک سرور انتخاب کنید و System proxy یا TUN را فعال کنید.",
        ],
        extra_tip=DEVICE_LIMIT_TIP,
    ),
    "v2box": GuideApp(
        id="v2box",
        name="V2Box",
        platforms="iOS / Android / macOS",
        steps=[
            "لینک اشتراک را از ربات دریافت کنید.",
            "V2Box → Add → Import from URL.",
            "لینک را وارد کنید و Subscribe/Update بزنید.",
            "پروفایل را انتخاب و Connect کنید.",
        ],
    ),
    "happ": GuideApp(
        id="happ",
        name="Happ",
        platforms="Android / iOS",
        steps=[
            "لینک اشتراک را از ربات کپی کنید.",
            "Happ → افزودن اشتراک → از لینک.",
            "لینک را Paste و ذخیره کنید.",
            "اشتراک را بروزرسانی و اتصال را برقرار کنید.",
        ],
    ),
    "v2raytun": GuideApp(
        id="v2raytun",
        name="v2RayTun",
        platforms="Android / iOS",
        steps=[
            "لینک اشتراک یا QR را از ربات بگیرید.",
            "v2RayTun → + → Import from clipboard یا Scan QR.",
            "پروفایل را انتخاب و اتصال را روشن کنید.",
        ],
    ),
}

PLATFORM_APPS: dict[str, list[str]] = {
    "android": ["v2rayng", "v2box", "v2raytun", "happ"],
    "ios": ["v2box", "v2raytun", "happ"],
    "desktop": ["v2rayn"],
    "macos": ["v2box"],
}


def format_app_guide(app_id: str) -> str:
    app = APPS[app_id]
    lines = [
        f"<b>📖 {app.name}</b> ({app.platforms})\n",
    ]
    for i, step in enumerate(app.steps, 1):
        lines.append(f"{i}. {step}")
    if app.extra_tip:
        lines.append(f"\n💡 {app.extra_tip}")
    return "\n".join(lines)


def format_platform_menu(platform: str) -> str:
    titles = {
        "android": "Android",
        "ios": "iOS",
        "desktop": "Windows / Linux",
        "macos": "macOS",
    }
    return f"<b>📖 راهنما — {titles.get(platform, platform)}</b>\n\nاپ مورد نظر را انتخاب کنید:"
