from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import DiscountCode, Order, OrderStatus, Payment, PaymentProvider, PaymentStatus, Plan
from bot.services.discount import DiscountService
from bot.services.payment.wallet import WalletService
from bot.services.provisioner import ProvisionerService
from bot.services.referral import ReferralService


class OrderService:
    def __init__(
        self,
        wallet: WalletService,
        discount: DiscountService,
        provisioner: ProvisionerService,
        referral: ReferralService,
    ) -> None:
        self._wallet = wallet
        self._discount = discount
        self._provisioner = provisioner
        self._referral = referral

    async def create_order(
        self,
        session: AsyncSession,
        user_id: int,
        plan: Plan,
        quantity: int,
        discount: DiscountCode | None = None,
        is_renewal: bool = False,
        renew_subscription_id: int | None = None,
    ) -> Order:
        subtotal = plan.price_toman * quantity
        total = subtotal
        if discount:
            total = self._discount.apply(discount, subtotal)
        order = Order(
            user_id=user_id,
            plan_id=plan.id,
            quantity=quantity,
            unit_price_toman=plan.price_toman,
            discount_id=discount.id if discount else None,
            total_toman=total,
            status=OrderStatus.PENDING,
            is_renewal=is_renewal,
            renew_subscription_id=renew_subscription_id,
        )
        session.add(order)
        await session.flush()
        return order

    async def pay_with_wallet(self, session: AsyncSession, order: Order, user_id: int) -> bool:
        try:
            await self._wallet.debit(
                session,
                user_id,
                order.total_toman,
                reference=f"ORD-{order.id}",
                note="خرید سرویس",
            )
        except ValueError:
            return False
        order.status = OrderStatus.PAID
        session.add(
            Payment(
                order_id=order.id,
                user_id=user_id,
                provider=PaymentProvider.WALLET,
                external_id=f"wallet_ORD-{order.id}",
                amount_toman=order.total_toman,
                status=PaymentStatus.COMPLETED,
            )
        )
        await session.flush()
        return True

    async def fulfill_order(
        self, session: AsyncSession, order: Order, plan: Plan, buyer_id: int
    ) -> list:
        from bot.db.models import TelegramUser

        buyer = await session.get(TelegramUser, buyer_id)
        if not buyer:
            return []

        if order.is_renewal and order.renew_subscription_id:
            from bot.db.models import Subscription

            sub = await session.get(Subscription, order.renew_subscription_id)
            if sub:
                ok = await self._provisioner.renew_subscription(session, sub, plan)
                order.status = OrderStatus.COMPLETED if ok else OrderStatus.FAILED
                await session.flush()
                return [sub] if ok else []

        results = await self._provisioner.provision_order(session, order, plan)
        if order.discount_id:
            from bot.db.models import DiscountCode

            dc = await session.get(DiscountCode, order.discount_id)
            if dc:
                await self._discount.consume(session, dc)

        await session.flush()
        return [r.subscription for r in results if r.subscription]
