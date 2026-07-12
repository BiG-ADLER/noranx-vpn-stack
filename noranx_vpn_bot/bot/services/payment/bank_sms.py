import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.models import Payment, PaymentProvider, PaymentStatus
from bot.services.payment.c2c_utils import parse_metadata, update_metadata
from bot.services.payment.completion import CompleteResult, complete_payment
from bot.services.orders import OrderService
from bot.services.payment.wallet import WalletService
from bot.utils.logging import get_logger

logger = get_logger("c2c")


@dataclass
class ParsedSms:
    amount_rial: int | None
    raw: str


class BankSmsParser(Protocol):
    def parse(self, raw_sms: str) -> ParsedSms: ...


class CustomBankParser:
    def __init__(self, patterns: list[str]) -> None:
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

    def parse(self, raw_sms: str) -> ParsedSms:
        amount_rial: int | None = None
        for pat in self._patterns:
            m = pat.search(raw_sms)
            if m:
                groups = m.groups()
                if groups:
                    raw_amount = re.sub(r"\D", "", groups[0])
                    if raw_amount:
                        amount_rial = int(raw_amount)
                        break
        if amount_rial is None:
            nums = re.findall(r"([\d,٬]+)\s*(?:ریال|rial)", raw_sms, re.IGNORECASE)
            if nums:
                amount_rial = int(re.sub(r"\D", "", nums[0]))
        return ParsedSms(amount_rial=amount_rial, raw=raw_sms)


def get_sms_parser(settings: Settings) -> BankSmsParser:
    try:
        patterns = json.loads(settings.c2c_sms_patterns)
        if not isinstance(patterns, list):
            patterns = []
    except json.JSONDecodeError:
        patterns = []
    if not patterns:
        patterns = [r"([\d,٬]+)\s*(?:ریال|rial)"]
    return CustomBankParser(patterns)


async def match_and_complete_sms_payment(
    session: AsyncSession,
    settings: Settings,
    *,
    amount_rial: int | None,
    raw_sms: str,
    order_service: OrderService,
) -> tuple[CompleteResult | None, Payment | None]:
    if not settings.c2c_sms_enabled:
        logger.info("sms_received but C2C_SMS_ENABLED=false")
        return None, None

    parsed = ParsedSms(amount_rial=amount_rial, raw=raw_sms)
    if amount_rial is None:
        parsed = get_sms_parser(settings).parse(raw_sms)
    if not parsed.amount_rial:
        logger.warning("sms_no_match: could not parse amount")
        return None, None

    amount_toman = parsed.amount_rial // 10
    payments = (
        await session.scalars(
            select(Payment).where(
                Payment.provider == PaymentProvider.C2C,
                Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.PENDING_REVIEW]),
                Payment.amount_toman == amount_toman,
            )
        )
    ).all()

    for payment in payments:
        meta = parse_metadata(payment)
        if meta.get("sms_matched_at"):
            continue
        update_metadata(
            payment,
            sms_matched_at=datetime.now(UTC).isoformat(),
            sms_raw=parsed.raw[:500],
        )
        result = await complete_payment(
            session,
            payment,
            order_service=order_service,
            wallet=WalletService(),
            source="bank_sms",
        )
        if result.error:
            logger.warning("sms match payment_id=%s error=%s", payment.id, result.error)
            continue
        logger.info("sms_matched_payment_id=%s amount_toman=%s", payment.id, amount_toman)
        return result, payment

    logger.warning("sms_no_match amount_toman=%s pending_count=%s", amount_toman, len(payments))
    return None, None
