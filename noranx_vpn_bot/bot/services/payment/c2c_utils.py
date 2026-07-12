import json
import re
import secrets
from datetime import UTC, datetime
from typing import Any

from bot.config import Settings


def generate_payment_ref() -> str:
    return f"NX-{secrets.token_hex(4).upper()}"


def mask_card(card: str) -> str:
    digits = re.sub(r"\D", "", card)
    if len(digits) < 8:
        return card
    return f"{digits[:4]}-****-****-{digits[-4:]}"


def format_card_display(card: str) -> str:
    digits = re.sub(r"\D", "", card)
    if len(digits) != 16:
        return card
    return "-".join(digits[i : i + 4] for i in range(0, 16, 4))


def build_c2c_metadata(
    payment_ref: str,
    base_toman: int,
    *,
    order_id: int | None = None,
    package_id: int | None = None,
) -> str:
    data: dict[str, Any] = {
        "type": "c2c_manual",
        "payment_ref": payment_ref,
        "base_toman": base_toman,
        "reject_reason": None,
    }
    if order_id is not None:
        data["order_id"] = order_id
    if package_id is not None:
        data["package_id"] = package_id
    return json.dumps(data, ensure_ascii=False)


def parse_metadata(payment) -> dict[str, Any]:
    if not payment.metadata_json:
        return {}
    try:
        return json.loads(payment.metadata_json)
    except json.JSONDecodeError:
        return {}


def update_metadata(payment, **fields: Any) -> None:
    meta = parse_metadata(payment)
    meta.update(fields)
    payment.metadata_json = json.dumps(meta, ensure_ascii=False)


def build_instructions(settings: Settings, payment_ref: str, amount_toman: int) -> str:
    if settings.c2c_mock:
        card_line = "کارت تست (حالت mock)"
    else:
        card = format_card_display(settings.c2c_dest_card)
        card_line = f"شماره کارت:\n<code>{card}</code>"
    name_line = ""
    if settings.c2c_dest_name and not settings.c2c_mock:
        name_line = f"\nبه نام: {settings.c2c_dest_name}"
    amount = f"{amount_toman:,}".replace(",", "٬")
    return (
        f"💳 پرداخت کارت به کارت\n\n"
        f"مبلغ: {amount} تومان\n"
        f"{card_line}{name_line}\n\n"
        f"شناسه پرداخت: <code>{payment_ref}</code>\n\n"
        f"پس از واریز، عکس رسید را همینجا بفرستید."
    )


def c2c_available(settings: Settings) -> bool:
    if not settings.c2c_enabled:
        return False
    if settings.c2c_mock:
        return True
    return bool(settings.c2c_dest_card.strip())


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
