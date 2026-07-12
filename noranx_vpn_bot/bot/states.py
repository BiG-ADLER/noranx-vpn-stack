from aiogram.fsm.state import State, StatesGroup


class ShopStates(StatesGroup):
    waiting_discount = State()
    waiting_custom_username = State()


class SupportStates(StatesGroup):
    waiting_category = State()
    waiting_message = State()
    user_reply = State()
    admin_reply = State()


class AdminStates(StatesGroup):
    search_user = State()
    wallet_adjust = State()
    create_discount = State()
    create_package = State()
    reply_ticket = State()
    c2c_reject_reason = State()
    marzban_extend_days = State()
    broadcast_message = State()
    broadcast_confirm = State()
    # Commerce
    plan_edit_value = State()
    plan_create = State()
    package_edit_amount = State()
    bot_copy_edit = State()
    setting_edit = State()
    # Guides
    guide_edit_text = State()
    # Messaging
    messaging_compose = State()
    messaging_confirm = State()
    messaging_single_id = State()
    # Ops
    report_schedule = State()
    anomaly_reenable_note = State()


class WalletStates(StatesGroup):
    waiting_crypto_usd_amount = State()


class PaymentStates(StatesGroup):
    waiting_c2c_receipt = State()
