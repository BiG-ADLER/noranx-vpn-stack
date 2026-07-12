import re
import secrets
import string

MARZBAN_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")


def generate_marzban_username(telegram_id: int, prefix: str = "") -> str:
    """Marzban: 3-32 chars, a-z, 0-9, underscore."""
    alphabet = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(8))
    base = f"tg{telegram_id}_{random_part}"
    if prefix:
        base = f"{prefix}{base}"
    return base[:32]


def normalize_marzban_username(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_")


def validate_marzban_username(name: str) -> str | None:
    """Return Persian error message or None if valid."""
    if not name:
        return "نام کاربری نمی‌تواند خالی باشد."
    if len(name) < 3:
        return "نام کاربری باید حداقل ۳ کاراکتر باشد."
    if len(name) > 32:
        return "نام کاربری حداکثر ۳۲ کاراکتر باشد."
    if not MARZBAN_USERNAME_RE.match(name):
        return "فقط حروف انگلیسی کوچک، اعداد و _ مجاز است."
    return None


def generate_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def generate_discount_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "NX" + "".join(secrets.choice(alphabet) for _ in range(6))
