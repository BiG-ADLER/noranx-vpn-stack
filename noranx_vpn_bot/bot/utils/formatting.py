from datetime import UTC, datetime


def _fa_num(n: int | float) -> str:
    s = f"{n:,.0f}" if isinstance(n, float) else f"{n:,}"
    return s.replace(",", "٬").replace(".", "/")


def format_toman(amount: int) -> str:
    return f"{_fa_num(amount)} تومان"


def format_irr(amount: int) -> str:
    return f"{_fa_num(amount)} ریال"


def format_usd_irr_line(irr_per_usd: int) -> str:
    toman = irr_per_usd // 10
    return f"1$ = {format_irr(irr_per_usd)} ({format_toman(toman)})"


def usd_to_toman(usd: float, irr_per_usd: int) -> int:
    return int(round(usd * irr_per_usd / 10))


def format_bytes(num: int) -> str:
    if num <= 0:
        return "نامحدود"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


def format_traffic_usage(used: int, limit: int | None) -> str:
    used_s = format_bytes(used) if used > 0 else "0 B"
    if not limit or limit <= 0:
        return f"{used_s} / نامحدود"
    return f"{used_s} / {format_bytes(limit)}"


def format_expiry(dt: datetime | None) -> str:
    if not dt:
        return "نامشخص"
    return dt.strftime("%Y/%m/%d %H:%M")


def days_until_expiry(dt: datetime | None) -> int | None:
    if not dt:
        return None
    now = datetime.now(UTC)
    exp = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return max(0, (exp.date() - now.date()).days)


def traffic_progress_bar(used: int, limit: int | None, width: int = 10) -> str:
    if not limit or limit <= 0:
        return "نامحدود"
    ratio = min(1.0, used / limit) if limit else 0
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(ratio * 100)
    return f"{bar} {pct}%"


def format_relative_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    now = datetime.now(UTC)
    created = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    delta = now - created
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} دقیقه پیش"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ساعت پیش"
    days = hours // 24
    return f"{days} روز پیش"
