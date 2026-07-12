"""Single source of truth for admin help sections and commands."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HelpCommand:
    cmd: str
    desc: str
    example: str | None = None


@dataclass(frozen=True)
class HelpAction:
    label: str
    callback_data: str


@dataclass(frozen=True)
class HelpSection:
    id: str
    emoji: str
    title: str
    intro: str
    commands: list[HelpCommand] = field(default_factory=list)
    actions: list[HelpAction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


SECTIONS: dict[str, HelpSection] = {
    "users": HelpSection(
        id="users",
        emoji="👥",
        title="کاربران و اشتراک",
        intro="جستجو، همگام‌سازی و فعال‌سازی مجدد حساب‌های Marzban.",
        commands=[
            HelpCommand(
                "ارسال شناسه تلگرام",
                "جستجوی کاربر (۵ تا ۱۵ رقم)",
                example="1020909704",
            ),
            HelpCommand(
                "/sync_user",
                "همگام‌سازی وضعیت اشتراک + limiter از Marzban",
                example="/sync_user tg1020909704_6q3vz6el",
            ),
            HelpCommand(
                "/re_enable",
                "فعال‌سازی مجدد اشتراک غیرفعال",
                example="/re_enable tg1020909704_6q3vz6el",
            ),
        ],
        actions=[
            HelpAction("👤 منوی کاربران", "admin:users"),
        ],
    ),
    "payments": HelpSection(
        id="payments",
        emoji="💳",
        title="پرداخت کارت به کارت",
        intro="بررسی، تأیید و رد پرداخت‌های C2C.",
        commands=[
            HelpCommand("/c2c_status", "جزئیات یک پرداخت", example="/c2c_status 42"),
            HelpCommand("/c2c_pending", "تعداد پرداخت‌های در انتظار"),
            HelpCommand("/c2c_test_channel", "تست ارسال به کانال بررسی"),
            HelpCommand(
                "/c2c_sim_approve",
                "شبیه‌سازی تأیید (تست)",
                example="/c2c_sim_approve 42",
            ),
        ],
        actions=[
            HelpAction("💳 لیست C2C", "admin:payments"),
        ],
        notes=["تأیید/رد از دکمه‌های inline روی رسید یا منوی پرداخت"],
    ),
    "wallet": HelpSection(
        id="wallet",
        emoji="💰",
        title="کیف پول",
        intro="تغییر دستی موجودی کاربران (در audit log ثبت می‌شود).",
        commands=[
            HelpCommand(
                "/wallet_add",
                "افزایش موجودی",
                example="/wallet_add 1020909704 50000",
            ),
            HelpCommand(
                "/wallet_sub",
                "کاهش موجودی",
                example="/wallet_sub 1020909704 10000",
            ),
        ],
        actions=[
            HelpAction("💰 منوی کیف پول", "admin:wallet"),
        ],
    ),
    "commerce": HelpSection(
        id="commerce",
        emoji="🛒",
        title="فروش، پلن‌ها و محتوا",
        intro="مدیریت پلن VPN، بسته شارژ، تخفیف و متن‌های ربات از منوی «فروش و پلن‌ها».",
        commands=[
            HelpCommand("/discount_new", "ساخت کد تخفیف درصدی", example="/discount_new 15 10"),
            HelpCommand("/package_add", "افزودن بسته شارژ", example="/package_add 100000"),
            HelpCommand("/package_toggle", "فعال/غیرفعال بسته", example="/package_toggle 3"),
        ],
        actions=[
            HelpAction("🛒 فروش و پلن‌ها", "admin:hub:commerce"),
            HelpAction("📋 پلن‌های VPN", "admin:plans"),
            HelpAction("📖 راهنمای اتصال", "admin:guides"),
        ],
    ),
    "orders": HelpSection(
        id="orders",
        emoji="📋",
        title="سفارش‌ها",
        intro="پیگیری سفارش‌های گیرکرده یا ناموفق.",
        commands=[
            HelpCommand(
                "/order_logs",
                "لاگ مراحل provisioning",
                example="/order_logs 9",
            ),
        ],
        actions=[
            HelpAction("📋 لیست سفارش‌ها", "admin:orders"),
        ],
    ),
    "marzban": HelpSection(
        id="marzban",
        emoji="🖥",
        title="Marzban",
        intro="مدیریت کاربران پنل: فعال/غیرفعال، تمدید، ریست ترافیک، sync.",
        commands=[],
        actions=[
            HelpAction("🖥 لیست کاربران", "admin:marzban:list:0"),
            HelpAction("🔍 Drift check", "admin:marzban:drift"),
        ],
        notes=[
            "روی هر کاربر: فعال، غیرفعال، +روز، ریست ترافیک، Sync DB، Import، حذف",
        ],
    ),
    "limiter": HelpSection(
        id="limiter",
        emoji="🔒",
        title="Limiter و زیرساخت",
        intro="وضعیت سلامت، limiter و ابزارهای ops.",
        commands=[
            HelpCommand("/debug", "گزارش سلامت کامل سیستم"),
            HelpCommand(
                "/limiter_check",
                "جزئیات limiter یک کاربر",
                example="/limiter_check tg1020909704_6q3vz6el",
            ),
            HelpCommand("/limiter_sync_all", "همگام‌سازی limiter همه اشتراک‌های فعال"),
        ],
        actions=[
            HelpAction("🔍 اجرای دیباگ", "admin:debug"),
        ],
        notes=[
            "اسکریپت سرور: ./scripts/limiter_audit.sh",
            "v2rayN: محدودیت با «بروزرسانی اشتراک» اعمال می‌شود",
        ],
    ),
    "support": HelpSection(
        id="support",
        emoji="🎫",
        title="پشتیبانی",
        intro="مدیریت کامل CRM تیکت: وضعیت، اولویت، مسئول، SLA، یادداشت داخلی.",
        commands=[
            HelpCommand("/ticket_stats", "آمار وضعیت و اولویت تیکت‌ها"),
            HelpCommand("/ticket_overdue", "لیست تیکت‌های overdue"),
        ],
        actions=[
            HelpAction("🎫 تیکت‌های باز", "admin:tickets"),
        ],
        notes=[
            "روی تیکت بزنید: پاسخ کاربر، یادداشت داخلی، وضعیت، اولویت، SLA.",
            "تیکت resolved/closed از سمت کاربر قابل پاسخ نیست.",
        ],
    ),
    "inbox": HelpSection(
        id="inbox",
        emoji="📥",
        title="صندوق عملیات",
        intro="نمای کلی کارهای در انتظار ادمین.",
        commands=[],
        actions=[
            HelpAction("📥 صندوق عملیات", "admin:inbox"),
        ],
    ),
    "broadcast": HelpSection(
        id="broadcast",
        emoji="📢",
        title="پیام‌رسانی",
        intro="ارسال مستقیم به کاربران غیرفعال است. فقط انتشار در کانال اصلی انجام می‌شود.",
        commands=[
            HelpCommand("/broadcast", "باز کردن مرکز اطلاع‌رسانی کانال"),
            HelpCommand("/audience_count", "نمایش سیاست پیام‌رسانی"),
        ],
        actions=[
            HelpAction("📢 انتشار در کانال", "admin:messaging"),
        ],
    ),
    "settings": HelpSection(
        id="settings",
        emoji="⚙️",
        title="تنظیمات",
        intro="تنظیمات env و مقادیر runtime در دیتابیس.",
        commands=[
            HelpCommand("/fx_rate", "نرخ فعلی USD/IRR"),
            HelpCommand("/fx_set", "تنظیم نرخ دستی", example="/fx_set 850000"),
            HelpCommand(
                "/setting_set",
                "تنظیم runtime در DB",
                example="/setting_set maintenance_mode true",
            ),
            HelpCommand("/report_now", "ارسال گزارش روزانه الان"),
            HelpCommand("/report_schedule", "زمان گزارش (تهران)", example="/report_schedule 9 30"),
        ],
        actions=[
            HelpAction("⚙️ تنظیمات و گزارش", "admin:hub:settings"),
            HelpAction("📊 گزارش روزانه", "admin:ops:report"),
        ],
    ),
}

SECTION_ORDER: list[str] = [
    "inbox",
    "users",
    "payments",
    "wallet",
    "commerce",
    "orders",
    "marzban",
    "limiter",
    "support",
    "broadcast",
    "settings",
]

TELEGRAM_ADMIN_COMMANDS: list[tuple[str, str]] = [
    ("admin", "پنل مدیریت"),
    ("help", "راهنمای ادمین"),
    ("debug", "وضعیت سیستم"),
    ("limiter_check", "بررسی limiter کاربر"),
    ("limiter_sync_all", "همگام limiter همه"),
    ("sync_user", "همگام‌سازی کاربر"),
    ("re_enable", "فعال‌سازی مجدد"),
    ("c2c_pending", "پرداخت‌های C2C"),
    ("c2c_status", "جزئیات پرداخت"),
    ("order_logs", "لاگ سفارش"),
    ("wallet_add", "افزایش کیف پول"),
    ("wallet_sub", "کاهش کیف پول"),
    ("discount_new", "ساخت کد تخفیف"),
    ("fx_rate", "نرخ ارز"),
    ("broadcast", "ارسال پیام گروهی"),
]


def format_section(section_id: str) -> str:
    sec = SECTIONS[section_id]
    lines = [
        f"<b>{sec.emoji} {sec.title}</b>",
        "",
        sec.intro,
        "",
    ]
    if sec.commands:
        lines.append("<b>دستورات</b>")
        for c in sec.commands:
            if c.example:
                lines.append(f"• <code>{c.example}</code>")
                lines.append(f"  {c.desc}")
            else:
                lines.append(f"• <code>{c.cmd}</code> — {c.desc}")
        lines.append("")
    if sec.notes:
        lines.append("<b>نکات</b>")
        for note in sec.notes:
            lines.append(f"• {note}")
        lines.append("")
    return "\n".join(lines).rstrip()


def all_commands_flat() -> list[tuple[str, HelpCommand]]:
    items: list[tuple[str, HelpCommand]] = []
    for sid in SECTION_ORDER:
        sec = SECTIONS[sid]
        for cmd in sec.commands:
            items.append((sec.title, cmd))
    return items


def format_commands_page(page: int, page_size: int = 8) -> tuple[str, int]:
    flat = all_commands_flat()
    total_pages = max(1, (len(flat) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    chunk = flat[page * page_size : (page + 1) * page_size]
    lines = [
        f"<b>📋 فهرست دستورات</b> — صفحه {page + 1}/{total_pages}",
        "",
    ]
    current_section = ""
    for section_title, cmd in chunk:
        if section_title != current_section:
            current_section = section_title
            lines.append(f"<b>{section_title}</b>")
        if cmd.example:
            lines.append(f"<code>{cmd.example}</code>")
            lines.append(f"↳ {cmd.desc}")
        else:
            lines.append(f"<code>{cmd.cmd}</code> — {cmd.desc}")
        lines.append("")
    return "\n".join(lines).rstrip(), total_pages


def find_section(query: str) -> str | None:
    q = query.strip().lower()
    if not q:
        return None
    aliases = {
        "user": "users",
        "users": "users",
        "کاربر": "users",
        "pay": "payments",
        "payment": "payments",
        "c2c": "payments",
        "wallet": "wallet",
        "کیف": "wallet",
        "discount": "commerce",
        "package": "commerce",
        "order": "orders",
        "marzban": "marzban",
        "limiter": "limiter",
        "debug": "limiter",
        "ticket": "support",
        "support": "support",
        "inbox": "inbox",
        "broadcast": "broadcast",
        "setting": "settings",
        "settings": "settings",
        "fx": "settings",
    }
    if q in aliases:
        return aliases[q]
    if q in SECTIONS:
        return q
    for sid, sec in SECTIONS.items():
        if q in sid or q in sec.title.lower():
            return sid
    return None
