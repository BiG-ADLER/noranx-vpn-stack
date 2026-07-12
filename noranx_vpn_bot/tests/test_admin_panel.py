"""Admin panel regression tests."""

import inspect

from bot.handlers.admin import tickets as tickets_mod
from bot.handlers.admin import users as users_mod
from bot.keyboards.admin import admin_tickets_kb
from bot.states import AdminStates


def test_ticket_view_callback_format():
    kb = admin_tickets_kb([(1, "open")])
    cb = kb.inline_keyboard[0][0].callback_data
    assert cb == "admin:ticket:view:1"


def test_refresh_ticket_view_helper_exists():
    assert hasattr(tickets_mod, "_refresh_ticket_view")
    sig = inspect.signature(tickets_mod._refresh_ticket_view)
    assert "ticket_id" in sig.parameters


def test_user_lookup_is_explicit_command_only():
    assert hasattr(users_mod, "lookup_user_cmd")
    assert not hasattr(users_mod, "lookup_telegram_id")


def test_admin_states_wired_for_inline_modules():
    assert AdminStates.package_edit_amount
    assert AdminStates.create_discount
    assert AdminStates.wallet_adjust
    assert AdminStates.setting_edit


def test_build_tickets_screen_exported():
    assert hasattr(tickets_mod, "build_tickets_screen")
