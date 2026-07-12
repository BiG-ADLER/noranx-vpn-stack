"""Tests for channel gate, referral wallet, and custom username."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.db.models import Referral, TelegramUser, WalletTxType
from bot.middlewares.channel import StrictChannelMiddleware
from bot.services.referral import ReferralService
from bot.utils.username import normalize_marzban_username, validate_marzban_username


def test_validate_marzban_username():
    assert validate_marzban_username("ab") is not None
    assert validate_marzban_username("a" * 33) is not None
    assert validate_marzban_username("MyVPN") is not None
    assert validate_marzban_username("bad-name") is not None
    assert validate_marzban_username("good_name1") is None


def test_normalize_marzban_username():
    assert normalize_marzban_username("  My_Name  ") == "my_name"


@pytest.mark.asyncio
async def test_referral_no_credit_without_referrer():
    session = AsyncMock()
    bot = AsyncMock()
    referee = TelegramUser(id=2, telegram_id=200, referred_by_id=None)
    svc = ReferralService()
    assert await svc.try_credit_referrer(session, bot, referee) is False


@pytest.mark.asyncio
async def test_referral_credit_idempotent():
    session = AsyncMock()
    session.scalar = AsyncMock(
        return_value=Referral(
            id=1,
            referrer_id=1,
            referee_id=2,
            rewarded_at=datetime.now(UTC),
        )
    )
    bot = AsyncMock()
    referee = TelegramUser(id=2, telegram_id=200, referred_by_id=1)
    svc = ReferralService()
    assert await svc.try_credit_referrer(session, bot, referee) is False


@pytest.mark.asyncio
async def test_referral_credit_amount_from_setting():
    session = AsyncMock()
    referral_row = Referral(id=1, referrer_id=1, referee_id=2, rewarded_at=None)
    referrer = TelegramUser(id=1, telegram_id=100, wallet_balance_toman=0)

    async def scalar(stmt):
        if "referrals" in str(stmt).lower():
            return referral_row
        return None

    session.scalar = scalar
    session.get = AsyncMock(return_value=referrer)
    session.add = MagicMock()
    session.flush = AsyncMock()

    bot = AsyncMock()
    referee = TelegramUser(id=2, telegram_id=200, referred_by_id=1)

    with patch("bot.services.referral.bot_content.get_referral_wallet_reward_toman", AsyncMock(return_value=15000)):
        with patch("bot.services.referral.WalletService") as WalletCls:
            wallet = WalletCls.return_value
            wallet.credit = AsyncMock(return_value=15000)
            svc = ReferralService()
            ok = await svc.try_credit_referrer(session, bot, referee)
            assert ok is True
            wallet.credit.assert_awaited_once()
            assert wallet.credit.await_args.args[2] == 15000


@pytest.mark.asyncio
async def test_strict_channel_blocks_callback():
    middleware = StrictChannelMiddleware()
    handler = AsyncMock()
    bot = AsyncMock()

    user = User(id=999, is_bot=False, first_name="T")
    chat = Chat(id=999, type="private")
    msg = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user)
    cb = CallbackQuery(id="1", from_user=user, chat_instance="x", data="menu:shop", message=msg)

    with patch("bot.middlewares.channel.gate.is_exempt", return_value=False):
        with patch("bot.middlewares.channel.gate.is_channel_member", AsyncMock(return_value=False)):
            with patch("bot.middlewares.channel.gate.send_gate_screen", AsyncMock()) as gate_screen:
                with patch("bot.middlewares.channel.safe_callback_answer", AsyncMock()):
                    result = await middleware(handler, cb, {"bot": bot})
                    assert result is None
                    handler.assert_not_awaited()
                    gate_screen.assert_awaited_once()


@pytest.mark.asyncio
async def test_strict_channel_allows_recheck():
    middleware = StrictChannelMiddleware()
    handler = AsyncMock(return_value="ok")
    bot = AsyncMock()
    user = User(id=999, is_bot=False, first_name="T")
    chat = Chat(id=999, type="private")
    msg = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user)
    cb = CallbackQuery(id="1", from_user=user, chat_instance="x", data="channel:recheck", message=msg)

    with patch("bot.middlewares.channel.gate.is_exempt", return_value=False):
        result = await middleware(handler, cb, {"bot": bot})
        assert result == "ok"
        handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_bypass_channel():
    middleware = StrictChannelMiddleware()
    handler = AsyncMock(return_value="ok")
    bot = AsyncMock()
    user = User(id=1, is_bot=False, first_name="A")
    chat = Chat(id=1, type="private")
    msg = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user)
    cb = CallbackQuery(id="1", from_user=user, chat_instance="x", data="menu:shop", message=msg)

    with patch("bot.middlewares.channel.gate.is_exempt", return_value=True):
        result = await middleware(handler, cb, {"bot": bot})
        assert result == "ok"
        handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_username_availability_db_collision():
    from bot.services.username_availability import is_username_available

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=42)
    marzban = AsyncMock()
    ok, err, name = await is_username_available(session, marzban, "taken_name")
    assert ok is False
    assert err is not None
    assert name is None


@pytest.mark.asyncio
async def test_provisioner_uses_preferred_username():
    from bot.db.models import Plan, TelegramUser
    from bot.services.provisioner import ProvisionerService

    settings = MagicMock()
    settings.provision_skip_limiters = True
    marzban = AsyncMock()
    marzban.create_user = AsyncMock(
        return_value=MagicMock(
            subscription_url="https://sub.example/x",
            data_limit=0,
        )
    )
    ip_lim = AsyncMock()
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    prov = ProvisionerService(settings, marzban, ip_lim)
    user = TelegramUser(id=1, telegram_id=111)
    plan = Plan(id=1, slug="p1", name_fa="P", device_count=1, price_toman=1000, duration_days=30)

    result = await prov.provision_one(
        session,
        user=user,
        plan=plan,
        device_limit=1,
        data_limit=0,
        duration_days=30,
        is_trial=False,
        correlation_id="TEST",
        preferred_username="myvpn123",
    )
    assert result.success
    marzban.create_user.assert_awaited_once()
    assert marzban.create_user.await_args.kwargs["username"] == "myvpn123"
