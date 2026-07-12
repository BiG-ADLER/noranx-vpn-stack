import json
from datetime import UTC, datetime

from fastapi import FastAPI, Header, Request, Response
from sqlalchemy import select

from bot.config import get_settings
from bot.db.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    SystemState,
    TelegramUser,
)
from bot.db.session import async_session_factory
from bot.services.ip_limiter import IpLimiterService
from bot.services.marzban import MarzbanService
from bot.services.orders import OrderService
from bot.services.discount import DiscountService
from bot.services.payment.bank_sms import match_and_complete_sms_payment
from bot.services.payment.c2c_base import get_c2c_adapter
from bot.services.payment.completion import (
    complete_payment,
    notify_order_fulfilled,
    notify_wallet_credited,
)
from bot.services.payment.nowpayments import NowPaymentsService
from bot.services.payment.wallet import WalletService
from bot.services.provisioner import ProvisionerService
from bot.services.referral import ReferralService
from bot.utils.logging import get_logger

logger = get_logger("webhooks")
app = FastAPI(title="NoranX Webhooks")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    from bot.services.readiness import run_readiness_checks

    return await run_readiness_checks()


@app.get("/webhooks/nowpayments")
async def nowpayments_get() -> dict:
    return {"status": "ok", "message": "POST IPN callbacks to this URL"}


def _order_service() -> OrderService:
    s = get_settings()
    return OrderService(
        WalletService(),
        DiscountService(),
        ProvisionerService(s, MarzbanService(s), IpLimiterService(s)),
        ReferralService(s),
    )


async def _set_state(key: str, value: str) -> None:
    async with async_session_factory() as session:
        row = await session.get(SystemState, key)
        if row:
            row.value = value
            row.updated_at = datetime.now(UTC)
        else:
            session.add(SystemState(key=key, value=value))
        await session.commit()


def _marzban_events(raw: object) -> list[dict]:
    """Marzban may POST a single event object or a batch (list of events)."""
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


async def _handle_marzban_event(session, event: dict) -> None:
    action = event.get("action", "")
    username = event.get("username", "")
    if not username:
        return

    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    if not sub:
        return

    user = await session.get(TelegramUser, sub.user_id)
    status_map = {
        "user_expired": SubscriptionStatus.EXPIRED,
        "user_disabled": SubscriptionStatus.DISABLED,
        "user_limited": SubscriptionStatus.LIMITED,
        "user_enabled": SubscriptionStatus.ACTIVE,
    }
    if action not in status_map:
        return

    sub.status = status_map[action]
    await session.flush()

    if user and action in ("user_expired", "user_limited", "user_disabled"):
        from bot.main import get_bot_instance

        bot = get_bot_instance()
        if bot:
            msgs = {
                "user_expired": "⏰ سرویس شما منقضی شد. برای تمدید از ربات اقدام کنید.",
                "user_limited": (
                    "📊 حجم سرویس شما تمام شد."
                    + (" (حداکثر ۱۰۰ مگابایت تست)" if sub.is_trial else "")
                ),
                "user_disabled": "🚫 سرویس شما به دلیل عبور از حد مجاز IP/دستگاه غیرفعال شد.",
            }
            try:
                await bot.send_message(user.telegram_id, msgs.get(action, ""))
            except Exception:
                pass


@app.post("/webhooks/marzban")
async def marzban_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
) -> Response:
    settings = get_settings()
    if settings.marzban_webhook_secret and x_webhook_secret != settings.marzban_webhook_secret:
        return Response(status_code=403)

    raw = await request.json()
    events = _marzban_events(raw)
    if not events:
        logger.warning("Marzban webhook ignored: unexpected payload type %s", type(raw).__name__)
        return Response(content='{"ok":true}', media_type="application/json")

    try:
        await _set_state("last_marzban_webhook", datetime.now(UTC).isoformat())

        async with async_session_factory() as session:
            for event in events:
                await _handle_marzban_event(session, event)
            await session.commit()
    except Exception:
        logger.exception("Marzban webhook processing failed")
        return Response(status_code=500, content='{"ok":false}', media_type="application/json")

    return Response(content='{"ok":true}', media_type="application/json")


@app.post("/webhooks/nowpayments")
async def nowpayments_webhook(request: Request) -> Response:
    settings = get_settings()
    body = await request.body()
    np = NowPaymentsService(settings)
    payload = np.verify_ipn(dict(request.headers), body)
    if not payload:
        return Response(status_code=403)

    payment_status = payload.get("payment_status") or payload.get("status")
    if payment_status not in ("finished", "confirmed", "FINISHED", "CONFIRMED"):
        return Response(content='{"ok":true}', media_type="application/json")

    external_id = str(payload.get("payment_id") or payload.get("invoice_id", ""))
    async with async_session_factory() as session:
        payment = await session.scalar(
            select(Payment).where(
                Payment.external_id == external_id,
                Payment.provider == PaymentProvider.NOWPAYMENTS,
            )
        )
        if not payment or payment.status == PaymentStatus.COMPLETED:
            return Response(content='{"ok":true}', media_type="application/json")

        svc = _order_service()
        result = await complete_payment(
            session,
            payment,
            order_service=svc,
            source="nowpayments",
        )
        if result.order_fulfilled or result.wallet_credited:
            user = await session.get(TelegramUser, payment.user_id)
            from bot.main import get_bot_instance

            bot = get_bot_instance()
            if user and bot:
                if result.order_fulfilled:
                    order = await session.get(Order, payment.order_id)
                    if order:
                        await notify_order_fulfilled(
                            bot,
                            session,
                            user,
                            order,
                            result.subscriptions,
                            header=f"✅ پرداخت کریپتو تأیید شد. سفارش #{order.id} فعال شد.",
                        )
                elif result.wallet_credited:
                    await notify_wallet_credited(
                        bot,
                        user,
                        payment.amount_toman,
                        header="✅ پرداخت کریپتو تأیید شد. کیف پول شارژ شد.",
                    )
        await session.commit()

    return Response(content='{"ok":true}', media_type="application/json")


@app.post("/webhooks/c2c")
async def c2c_webhook(
    request: Request,
    x_c2c_secret: str | None = Header(default=None),
) -> Response:
    settings = get_settings()
    body = await request.body()
    adapter = get_c2c_adapter(settings)
    verified = await adapter.verify_webhook(
        {"x-c2c-secret": x_c2c_secret or ""}, body
    )
    if not verified:
        return Response(status_code=403)

    async with async_session_factory() as session:
        existing = await session.scalar(
            select(Payment).where(
                Payment.external_id == verified.external_id,
                Payment.provider == PaymentProvider.C2C,
            )
        )
        if existing and existing.status == PaymentStatus.COMPLETED:
            return Response(content='{"ok":true}', media_type="application/json")

        if not existing:
            existing = Payment(
                user_id=verified.user_id,
                order_id=verified.order_id,
                recharge_package_id=verified.package_id,
                provider=PaymentProvider.C2C,
                external_id=verified.external_id,
                amount_toman=verified.amount_toman,
                status=PaymentStatus.PENDING_REVIEW,
            )
            session.add(existing)
            await session.flush()

        svc = _order_service()
        result = await complete_payment(
            session,
            existing,
            order_service=svc,
            source="c2c_mock_webhook",
        )
        if result.order_fulfilled or result.wallet_credited:
            user = await session.get(TelegramUser, existing.user_id)
            from bot.main import get_bot_instance

            bot = get_bot_instance()
            if user and bot:
                if result.order_fulfilled and existing.order_id:
                    order = await session.get(Order, existing.order_id)
                    if order:
                        await notify_order_fulfilled(
                            bot,
                            session,
                            user,
                            order,
                            result.subscriptions,
                            header=f"✅ پرداخت تست C2C تأیید شد. سفارش #{order.id} فعال شد.",
                        )
                elif result.wallet_credited:
                    await notify_wallet_credited(
                        bot,
                        user,
                        existing.amount_toman,
                        header="✅ پرداخت تست C2C — کیف پول شارژ شد.",
                    )
        await session.commit()

    return Response(content='{"ok":true}', media_type="application/json")


@app.post("/webhooks/bank-sms")
async def bank_sms_webhook(
    request: Request,
    x_c2c_secret: str | None = Header(default=None),
) -> Response:
    settings = get_settings()
    if x_c2c_secret != settings.c2c_webhook_secret:
        return Response(status_code=403)

    if not settings.c2c_sms_enabled:
        return Response(content='{"ok":true,"skipped":true}', media_type="application/json")

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return Response(status_code=400)

    raw_sms = str(payload.get("raw_sms", ""))
    amount_rial = payload.get("amount_rial")
    if amount_rial is not None:
        amount_rial = int(amount_rial)

    async with async_session_factory() as session:
        result, payment = await match_and_complete_sms_payment(
            session,
            settings,
            amount_rial=amount_rial,
            raw_sms=raw_sms,
            order_service=_order_service(),
        )
        if result and payment:
            user = await session.get(TelegramUser, payment.user_id)
            from bot.main import get_bot_instance

            bot = get_bot_instance()
            if user and bot:
                if result.order_fulfilled and payment.order_id:
                    order = await session.get(Order, payment.order_id)
                    if order:
                        await notify_order_fulfilled(
                            bot,
                            session,
                            user,
                            order,
                            result.subscriptions,
                            header=f"✅ پرداخت کارت به کارت (SMS) تأیید شد. سفارش #{order.id}",
                        )
                elif result.wallet_credited:
                    await notify_wallet_credited(
                        bot,
                        user,
                        payment.amount_toman,
                        header="✅ پرداخت کارت به کارت (SMS) — کیف پول شارژ شد.",
                    )
            if settings.c2c_review_channel_id and bot:
                try:
                    await bot.send_message(
                        settings.c2c_review_channel_id,
                        f"🤖 auto-approved via SMS — payment #{payment.id}",
                    )
                except Exception:
                    pass
        await session.commit()

    return Response(content='{"ok":true}', media_type="application/json")


@app.post("/webhooks/c2c/mock/{external_id}")
async def c2c_mock_trigger(external_id: str) -> Response:
    """Test endpoint to simulate C2C payment when C2C_MOCK=true."""
    settings = get_settings()
    if not settings.c2c_mock:
        return Response(status_code=404)
    from starlette.requests import Request as StarletteRequest

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"x-c2c-secret", settings.c2c_webhook_secret.encode())],
    }
    body = json.dumps({"external_id": external_id}).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    req = StarletteRequest(scope, receive)
    return await c2c_webhook(req, x_c2c_secret=settings.c2c_webhook_secret)
