from aiogram import Router

from bot.handlers.admin import (
    commerce,
    debug,
    discounts,
    guides,
    help as admin_help,
    inbox,
    marzban,
    messaging,
    ops,
    orders,
    packages,
    payments,
    settings,
    tickets,
    user_directory,
    users,
    wallet as admin_wallet,
)
from bot.handlers.common import cancel
from bot.handlers.user import (
    accounts,
    c2c_receipt,
    channel_gate,
    guide,
    referral,
    shop,
    start,
    support,
    trial,
    wallet,
)


def setup_routers() -> Router:
    root = Router()
    root.include_router(cancel.router)
    root.include_router(start.router)
    root.include_router(shop.router)
    root.include_router(accounts.router)
    root.include_router(wallet.router)
    root.include_router(c2c_receipt.router)
    root.include_router(trial.router)
    root.include_router(referral.router)
    root.include_router(support.router)
    root.include_router(guide.router)
    root.include_router(channel_gate.router)
    root.include_router(orders.router)
    root.include_router(payments.router)
    root.include_router(marzban.router)
    root.include_router(commerce.router)
    root.include_router(tickets.router)
    root.include_router(guides.router)
    root.include_router(packages.router)
    root.include_router(discounts.router)
    root.include_router(admin_wallet.router)
    root.include_router(settings.router)
    root.include_router(users.router)
    root.include_router(user_directory.router)
    root.include_router(admin_help.router)
    root.include_router(ops.router)
    root.include_router(inbox.router)
    root.include_router(messaging.router)
    root.include_router(debug.router)
    return root
