from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    ProvisioningLog,
    Subscription,
    SubscriptionStatus,
    SupportTicket,
    SystemState,
    TicketPriority,
    TicketStatus,
    TrafficAnomalyEvent,
    TrafficAnomalyStatus,
    TrafficUsageSnapshot,
)
from bot.services.registry import get_ip_limiter, get_marzban, get_sync_service
from bot.services.traffic_anomaly import TrafficAnomalyService
from bot.handlers.user.shop import _get_services
from bot.services.payment.c2c_utils import parse_metadata
from bot.services.payment.completion import complete_payment
from bot.services.payment.nowpayments import NowPaymentsService
from bot.services.payment.wallet import WalletService
from bot.keyboards.admin_inbox import debug_actions_kb

router = Router()


async def build_debug_report(session: AsyncSession) -> str:
    settings = get_settings()
    marzban = get_marzban()
    ip_lim = get_ip_limiter()

    m_ok, m_msg, m_ms = await marzban.health_check()
    i_ok, i_msg, i_ms = await ip_lim.health_check()
    np_ok, np_msg = await NowPaymentsService(settings).health_check()

    stuck = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING)
    )
    since = datetime.now(UTC) - timedelta(hours=24)
    failures = await session.scalar(
        select(func.count())
        .select_from(ProvisioningLog)
        .where(ProvisioningLog.ok.is_(False), ProvisioningLog.created_at >= since)
    )
    sync = get_sync_service()
    drift = await sync.count_limiter_drift(session)
    active_subs = await session.scalar(
        select(func.count())
        .select_from(Subscription)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
    )

    last_wh = await session.get(SystemState, "last_marzban_webhook")
    wh_text = last_wh.value if last_wh else "never"

    try:
        from sqlalchemy import text

        await session.execute(text("SELECT 1"))
        pg_ok = "OK"
    except Exception as e:
        pg_ok = str(e)

    try:
        from bot.services.readiness import get_redis_client

        r = await get_redis_client()
        await r.ping()
        redis_ok = "OK"
    except Exception as e:
        redis_ok = str(e)

    from bot.services.readiness import format_readiness_summary, run_readiness_checks

    ready_summary = format_readiness_summary(await run_readiness_checks())

    node_lines = []
    try:
        nodes = await marzban.list_nodes()
        for n in nodes[:5]:
            node_lines.append(f"  {n.get('name', '?')}: {n.get('status', '?')}")
    except Exception as e:
        node_lines.append(f"  (unavailable: {e})")

    prov_failures = (
        await session.scalars(
            select(ProvisioningLog)
            .where(ProvisioningLog.ok.is_(False), ProvisioningLog.created_at >= since)
            .order_by(ProvisioningLog.id.desc())
            .limit(5)
        )
    ).all()
    fail_lines = [
        f"  ❌ #{l.order_id} {l.step}: {(l.error or '')[:60]}"
        for l in prov_failures
    ]

    sub_host = settings.public_subscription_host
    sub_ok = "?"
    try:
        import httpx as hx
        async with hx.AsyncClient(timeout=5.0) as hc:
            r = await hc.head(f"{settings.public_subscription_scheme}://{sub_host}/")
            sub_ok = str(r.status_code)
    except Exception as e:
        sub_ok = f"FAIL ({e})"

    lines = [
        "🔍 <b>دیباگ سیستم</b>\n",
        f"Marzban API: {'OK' if m_ok else 'FAIL'} ({m_ms}ms) — {m_msg}",
        f"IP Limiter: {'OK' if i_ok else 'FAIL'} ({i_ms}ms) — {i_msg}",
        f"NowPayments: {'OK' if np_ok else 'FAIL'} — {np_msg}",
        f"PostgreSQL: {pg_ok}",
        f"Redis: {redis_ok}",
        ready_summary,
        f"Stuck orders: {stuck}",
        f"Provisioning failures (24h): {failures}",
        f"Limiter drift count: {drift}",
        f"Active subs: {active_subs or 0}",
        f"Last Marzban webhook: {wh_text}",
        f"Public sub ({sub_host}): {sub_ok}",
    ]
    if node_lines:
        lines.append("Nodes:")
        lines.extend(node_lines)
    if fail_lines:
        lines.append("Recent prov. failures:")
        lines.extend(fail_lines)

    from bot.db.models import GuideApp, GuidePlatform, NotificationLog, Plan
    from bot.services import bot_content
    from bot.services.audience import AudienceSegment, count_segment
    from bot.services.reports import get_digest_schedule

    plan_count = await session.scalar(select(func.count()).select_from(Plan))
    guide_plat = await session.scalar(select(func.count()).select_from(GuidePlatform))
    guide_apps = await session.scalar(select(func.count()).select_from(GuideApp))
    enabled, dh, dm = await get_digest_schedule(session)
    maint = await bot_content.is_maintenance_mode(session)
    ops_ch = await bot_content.get_setting(session, "ops_channel_id") or str(settings.ops_channel_id)
    ann_ch = await bot_content.get_setting(session, "announcement_channel_id") or str(
        settings.announcement_channel_id
    )
    seg_lines = []
    for seg in (
        AudienceSegment.ALL_STARTED,
        AudienceSegment.NEVER_PURCHASED,
        AudienceSegment.ACTIVE_SUBSCRIBERS,
        AudienceSegment.EXPIRED,
    ):
        seg_lines.append(f"  {seg.value}: {await count_segment(session, seg)}")
    recent_alerts = (
        await session.scalars(
            select(NotificationLog).order_by(NotificationLog.id.desc()).limit(5)
        )
    ).all()
    lines.extend(
        [
            "",
            f"Plans: {plan_count} | Guide platforms: {guide_plat} apps: {guide_apps}",
            f"Digest: {'on' if enabled else 'off'} {dh:02d}:{dm:02d} Tehran",
            f"Maintenance: {maint} | Ops ch: {ops_ch or '—'} | Ann ch: {ann_ch or '—'}",
            "Audience:",
            *seg_lines,
        ]
    )
    if recent_alerts:
        lines.append("Recent alerts:")
        for a in recent_alerts:
            lines.append(f"  [{a.severity}] {a.dedup_key}: {a.body[:40]}…")
    return "\n".join(lines)


@router.callback_query(F.data == "admin:debug")
async def admin_debug_callback(callback, session: AsyncSession) -> None:
    if callback.from_user.id not in get_settings().admin_ids:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    report = await build_debug_report(session)
    await callback.message.edit_text(report, reply_markup=debug_actions_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(Command("debug"))
async def admin_debug_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    report = await build_debug_report(session)
    await message.answer(report, reply_markup=debug_actions_kb(), parse_mode="HTML")


@router.message(Command("c2c_status"))
async def c2c_status_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("استفاده: /c2c_status <payment_id>")
        return
    payment = await session.get(Payment, int(parts[1]))
    if not payment:
        await message.answer("پرداخت یافت نشد.")
        return
    meta = parse_metadata(payment)
    await message.answer(
        f"Payment #{payment.id}\n"
        f"provider: {payment.provider.value}\n"
        f"status: {payment.status.value}\n"
        f"amount: {payment.amount_toman}\n"
        f"external_id: {payment.external_id}\n"
        f"order_id: {payment.order_id}\n"
        f"recharge_package_id: {payment.recharge_package_id}\n"
        f"user_id: {payment.user_id}\n"
        f"metadata: {meta}",
        parse_mode=None,
    )


@router.message(Command("c2c_pending"))
async def c2c_pending_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from sqlalchemy import func, select

    pending = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.provider == PaymentProvider.C2C,
            Payment.status == PaymentStatus.PENDING,
        )
    )
    review = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.provider == PaymentProvider.C2C,
            Payment.status == PaymentStatus.PENDING_REVIEW,
        )
    )
    await message.answer(
        f"C2C pending (no receipt): {pending or 0}\n"
        f"C2C pending_review: {review or 0}",
        parse_mode=None,
    )


@router.message(Command("c2c_test_channel"))
async def c2c_test_channel_cmd(message: Message) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    settings = get_settings()
    if not settings.c2c_review_channel_id:
        await message.answer("C2C_REVIEW_CHANNEL_ID تنظیم نشده.")
        return
    try:
        await message.bot.send_message(
            settings.c2c_review_channel_id,
            "🧪 تست کانال بررسی پرداخت C2C",
        )
        await message.answer("پیام تست ارسال شد.")
    except Exception as e:
        await message.answer(f"خطا: {e}")


@router.message(Command("c2c_sim_approve"))
async def c2c_sim_approve_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("استفاده: /c2c_sim_approve <payment_id>")
        return
    payment = await session.get(Payment, int(parts[1]))
    if not payment or payment.provider != PaymentProvider.C2C:
        await message.answer("پرداخت C2C یافت نشد.")
        return
    result = await complete_payment(
        session,
        payment,
        order_service=_get_services(),
        wallet=WalletService(),
        source="admin_sim_approve",
    )
    await session.commit()
    await message.answer(
        f"result: already={result.already_completed} "
        f"order={result.order_fulfilled} wallet={result.wallet_credited} "
        f"error={result.error}",
        parse_mode=None,
    )


@router.message(Command("fx_rate"))
async def fx_rate_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.services.exchange_rate import ExchangeRateError, ExchangeRateService
    from bot.utils.formatting import format_usd_irr_line

    try:
        rate = await ExchangeRateService().get_rate(session)
        await message.answer(
            f"{format_usd_irr_line(rate.irr_per_usd)}\n"
            f"source: {rate.source}\n"
            f"age: {int(rate.age_seconds)}s",
            parse_mode=None,
        )
    except ExchangeRateError as e:
        await message.answer(str(e))


@router.message(Command("fx_set"))
async def fx_set_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.services.exchange_rate import ExchangeRateService, set_manual_rate

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("استفاده: /fx_set <irr_per_usd>")
        return
    irr = int(parts[1])
    await set_manual_rate(session, irr)
    await session.commit()
    await message.answer(f"Manual rate set: {irr} IRR/USD")


@router.message(Command("limiter_check"))
async def limiter_check_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.services.ip_limiter import IpLimiterService
    from bot.db.models import Subscription

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("استفاده: /limiter_check <username>")
        return
    username = parts[1].strip()
    ip = IpLimiterService(get_settings())
    ip_lim = await ip.get_limit(username)
    sub = await session.scalar(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    await message.answer(
        "IP limiter:\n"
        f"  config={ip_lim}\n\n"
        f"Bot DB: device={sub.device_limit if sub else 'N/A'} (cosmetic) "
        f"ip={sub.ip_limit if sub else 'N/A'}",
        parse_mode=None,
    )


@router.message(Command("limiter_sync_all"))
async def limiter_sync_all_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.db.models import Subscription, SubscriptionStatus

    sync = get_sync_service()
    subs = (
        await session.scalars(
            select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)
        )
    ).all()
    ok = sum(1 for sub in subs if await sync.sync_limiters_for_subscription(sub))
    await message.answer(f"Synced {ok}/{len(subs)} active subscriptions.", parse_mode=None)


@router.message(Command("ticket_stats"))
async def ticket_stats_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    status_lines = []
    for st in TicketStatus:
        c = await session.scalar(
            select(func.count()).select_from(SupportTicket).where(SupportTicket.status == st)
        )
        status_lines.append(f"{st.value}: {c or 0}")
    prio_lines = []
    for pr in TicketPriority:
        c = await session.scalar(
            select(func.count()).select_from(SupportTicket).where(SupportTicket.priority == pr)
        )
        prio_lines.append(f"{pr.value}: {c or 0}")
    await message.answer(
        "Ticket stats\n\nStatus:\n"
        + "\n".join(status_lines)
        + "\n\nPriority:\n"
        + "\n".join(prio_lines),
        parse_mode=None,
    )


@router.message(Command("ticket_overdue"))
async def ticket_overdue_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    now = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(SupportTicket)
            .where(
                SupportTicket.due_at.isnot(None),
                SupportTicket.due_at < now,
                SupportTicket.status.notin_([TicketStatus.CLOSED, TicketStatus.RESOLVED]),
            )
            .order_by(SupportTicket.due_at.asc())
            .limit(20)
        )
    ).all()
    if not rows:
        await message.answer("overdue ticket نداریم.", parse_mode=None)
        return
    lines = ["Overdue tickets:"]
    for t in rows:
        lines.append(f"#{t.id} {t.title[:24]} due={t.due_at.isoformat()} status={t.status.value}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("channel_post_check"))
async def channel_post_check_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.services.notification_hub import NotificationHub

    hub = NotificationHub(message.bot, session)
    ok = await hub.notify_announcement_channel("Channel post check from debug command.")
    await message.answer("ارسال کانال OK" if ok else "ارسال کانال ناموفق", parse_mode=None)


@router.message(Command("anomaly_stats"))
async def anomaly_stats_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    lines = ["Traffic anomaly stats:"]
    for st in TrafficAnomalyStatus:
        c = await session.scalar(
            select(func.count()).select_from(TrafficAnomalyEvent).where(TrafficAnomalyEvent.status == st)
        )
        lines.append(f"{st.value}: {c or 0}")
    recent = await session.scalar(
        select(func.count())
        .select_from(TrafficAnomalyEvent)
        .where(TrafficAnomalyEvent.created_at >= datetime.now(UTC) - timedelta(hours=24))
    )
    lines.append(f"last_24h: {recent or 0}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("anomaly_recent"))
async def anomaly_recent_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    rows = (
        await session.scalars(
            select(TrafficAnomalyEvent).order_by(TrafficAnomalyEvent.id.desc()).limit(20)
        )
    ).all()
    if not rows:
        await message.answer("رخداد anomaly ثبت نشده.", parse_mode=None)
        return
    lines = ["Recent anomaly events:"]
    for e in rows:
        lines.append(
            f"#{e.id} {e.marzban_username} {e.status.value} score={e.score} "
            f"delta={e.delta_bytes}b/{e.delta_minutes}m"
        )
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("anomaly_user"))
async def anomaly_user_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("استفاده: /anomaly_user <username>")
        return
    username = parts[1].strip()
    snaps = (
        await session.scalars(
            select(TrafficUsageSnapshot)
            .where(TrafficUsageSnapshot.marzban_username == username)
            .order_by(TrafficUsageSnapshot.checked_at.desc())
            .limit(10)
        )
    ).all()
    events = (
        await session.scalars(
            select(TrafficAnomalyEvent)
            .where(TrafficAnomalyEvent.marzban_username == username)
            .order_by(TrafficAnomalyEvent.created_at.desc())
            .limit(10)
        )
    ).all()
    lines = [f"user={username}", "Snapshots:"]
    for s in snaps:
        lines.append(f"{s.checked_at.isoformat()} used={s.used_traffic_bytes}")
    lines.append("Events:")
    for e in events:
        lines.append(f"{e.created_at.isoformat()} {e.status.value} score={e.score} action={e.action_taken}")
    await message.answer("\n".join(lines[:80]), parse_mode=None)


@router.message(Command("anomaly_recheck"))
async def anomaly_recheck_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("استفاده: /anomaly_recheck <username>")
        return
    username = parts[1].strip()
    settings = get_settings()
    marzban = MarzbanService(settings)
    service = TrafficAnomalyService(settings, marzban)
    users, _ = await marzban.list_users(search=username, limit=1)
    if not users:
        await message.answer("کاربر در Marzban پیدا نشد.", parse_mode=None)
        return
    result = await service.evaluate_user(session, users[0], dry_run=True, bot=None)
    if not result:
        await message.answer("داده کافی برای ارزیابی نیست (snapshot اولیه ذخیره شد).", parse_mode=None)
        return
    await message.answer(
        f"user={result.username}\n"
        f"action={result.action}\n"
        f"score={result.score}\n"
        f"delta={result.delta_bytes} bytes / {result.delta_minutes} min\n"
        f"rate={result.rate_mbps:.3f} Mbps\n"
        f"reasons={','.join(result.reasons) or '-'}",
        parse_mode=None,
    )


@router.message(Command("anomaly_cleanup"))
async def anomaly_cleanup_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    settings = get_settings()
    service = TrafficAnomalyService(settings, MarzbanService(settings))
    deleted_snapshots, deleted_events = await service.cleanup_old_data(session, days=30)
    await message.answer(
        f"cleanup done snapshots={deleted_snapshots} events={deleted_events}",
        parse_mode=None,
    )


@router.message(Command("channel_check"))
async def channel_check_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.services.channel_gate import is_channel_member, is_exempt, resolve_channel_link

    parts = (message.text or "").split(maxsplit=1)
    tg_id = int(parts[1].strip()) if len(parts) > 1 else message.from_user.id
    settings = get_settings()
    link = await resolve_channel_link(message.bot)
    exempt = is_exempt(tg_id)
    member = await is_channel_member(message.bot, tg_id) if not exempt else True
    status = "exempt (admin or disabled)" if exempt else ("member" if member else "not_member")
    await message.answer(
        f"channel_check tg_id={tg_id}\n"
        f"required_channel_id={settings.required_channel_id or '—'}\n"
        f"link={link or '—'}\n"
        f"status={status}",
        parse_mode=None,
    )


@router.message(Command("referral_status"))
async def referral_status_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.db.models import Referral, TelegramUser, WalletTransaction

    parts = (message.text or "").split(maxsplit=1)
    tg_id = int(parts[1].strip()) if len(parts) > 1 else message.from_user.id
    user = await session.scalar(select(TelegramUser).where(TelegramUser.telegram_id == tg_id))
    if not user:
        await message.answer("کاربر یافت نشد.", parse_mode=None)
        return
    as_referee = await session.scalar(select(Referral).where(Referral.referee_id == user.id))
    referrer = None
    if user.referred_by_id:
        referrer = await session.get(TelegramUser, user.referred_by_id)
    refs_given = (
        await session.scalars(select(Referral).where(Referral.referrer_id == user.id))
    ).all()
    wallet_refs = (
        await session.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user.id, WalletTransaction.reference.like("REF-%"))
            .order_by(WalletTransaction.id.desc())
            .limit(5)
        )
    ).all()
    lines = [
        f"user id={user.id} tg={user.telegram_id}",
        f"referred_by={referrer.telegram_id if referrer else '—'}",
        f"as_referee rewarded_at={as_referee.rewarded_at if as_referee else '—'}",
        f"referrals_given={len(refs_given)}",
    ]
    for tx in wallet_refs:
        lines.append(f"wallet_ref {tx.reference} amount={tx.amount_toman} at={tx.created_at}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("referral_simulate_credit"))
async def referral_simulate_credit_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.db.models import TelegramUser
    from bot.services.referral import ReferralService

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("استفاده: /referral_simulate_credit <telegram_id>", parse_mode=None)
        return
    tg_id = int(parts[1].strip())
    user = await session.scalar(select(TelegramUser).where(TelegramUser.telegram_id == tg_id))
    if not user:
        await message.answer("کاربر یافت نشد.", parse_mode=None)
        return
    ok = await ReferralService().try_credit_referrer(session, message.bot, user)
    await message.answer("credited" if ok else "skipped or failed", parse_mode=None)


@router.message(Command("username_check"))
async def username_check_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.services.marzban import MarzbanService
    from bot.services.username_availability import is_username_available
    from bot.utils.username import validate_marzban_username, normalize_marzban_username

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("استفاده: /username_check <name>", parse_mode=None)
        return
    raw = parts[1].strip()
    normalized = normalize_marzban_username(raw)
    fmt_err = validate_marzban_username(normalized)
    if fmt_err:
        await message.answer(f"format_error: {fmt_err}", parse_mode=None)
        return
    ok, err, name = await is_username_available(session, MarzbanService(get_settings()), raw)
    await message.answer(
        f"name={name}\navailable={ok}\nerror={err or '—'}",
        parse_mode=None,
    )


@router.message(Command("gate_trace"))
async def gate_trace_cmd(message: Message) -> None:
    if message.from_user.id not in get_settings().admin_ids:
        return
    from bot.middlewares.channel import set_gate_trace, is_gate_trace

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip().lower() not in ("on", "off"):
        state = "on" if is_gate_trace(message.from_user.id) else "off"
        await message.answer(f"gate_trace is {state}. Usage: /gate_trace on|off", parse_mode=None)
        return
    enabled = parts[1].strip().lower() == "on"
    set_gate_trace(message.from_user.id, enabled)
    await message.answer(f"gate_trace {'enabled' if enabled else 'disabled'}", parse_mode=None)
