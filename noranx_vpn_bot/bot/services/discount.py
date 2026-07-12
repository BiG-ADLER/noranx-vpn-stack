from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import DiscountCode, DiscountType


class DiscountService:
    async def validate(
        self,
        session: AsyncSession,
        code: str,
        user_id: int,
        plan_slug: str,
        subtotal_toman: int,
    ) -> tuple[DiscountCode | None, str]:
        dc = await session.scalar(
            select(DiscountCode).where(DiscountCode.code == code.upper(), DiscountCode.is_active)
        )
        if not dc:
            return None, "کد تخفیف نامعتبر است."
        now = datetime.now(UTC)
        if dc.valid_from and now < dc.valid_from:
            return None, "کد تخفیف هنوز فعال نیست."
        if dc.valid_until and now > dc.valid_until:
            return None, "کد تخفیف منقضی شده است."
        if dc.used_count >= dc.max_uses:
            return None, "ظرفیت استفاده از این کد تمام شده است."
        if subtotal_toman < dc.min_order_toman:
            return None, f"حداقل مبلغ سفارش {dc.min_order_toman:,} تومان است."
        if dc.applicable_plan_slugs:
            slugs = [s.strip() for s in dc.applicable_plan_slugs.split(",")]
            if plan_slug not in slugs:
                return None, "این کد برای این پلن قابل استفاده نیست."
        return dc, ""

    def apply(self, dc: DiscountCode, subtotal_toman: int) -> int:
        if dc.discount_type == DiscountType.PERCENT:
            discount = subtotal_toman * dc.value // 100
        else:
            discount = dc.value
        return max(subtotal_toman - discount, 0)

    async def consume(self, session: AsyncSession, dc: DiscountCode) -> None:
        dc.used_count += 1
        await session.flush()
