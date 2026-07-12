from bot.keyboards.admin import admin_menu_kb
from bot.keyboards.admin_inbox import debug_actions_kb, inbox_kb
from bot.keyboards.connect_guide import guide_root_kb
from bot.services.admin_ops import OpsSnapshot


def test_admin_menu_kb_renders():
    snap = OpsSnapshot(1, 2, 3, 0, 1, 0, True, False)
    kb = admin_menu_kb(snap)
    assert kb.inline_keyboard


def test_inbox_kb_renders():
    snap = OpsSnapshot(0, 0, 0, 0, 0, 0, True, True)
    kb = inbox_kb(snap)
    assert kb.inline_keyboard


def test_debug_actions_kb():
    assert debug_actions_kb().inline_keyboard


def test_guide_root_kb():
    assert guide_root_kb().inline_keyboard
