from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin.users import _is_admin
from bot.keyboards.admin_hubs import commerce_hub_kb
from bot.keyboards.common import back_to_admin_kb, cancel_fsm_kb
from bot.services import bot_content, plans as plan_svc
from bot.services.plans import PlanValidationError
from bot.states import AdminStates
from bot.utils.telegram import safe_callback_answer
from aiogram.fsm.context import FSMContext

router = Router()

COPY_FIELDS = {
    "welcome": ("bot_welcome_text", "متن خوش‌آمدگویی"),
    "welcome_new": ("bot_welcome_new_text", "متن خوش‌آمد کاربر جدید"),
    "shop": ("bot_shop_header", "عنوان فروشگاه"),
    "admin": ("bot_admin_panel_title", "عنوان پنل ادمین"),
}


def _plan_actions_kb(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ نام", callback_data=f"admin:plan:edit:name:{plan_id}"),
                InlineKeyboardButton(text="💰 قیمت", callback_data=f"admin:plan:edit:price:{plan_id}"),
            ],
            [
                InlineKeyboardButton(text="📱 دستگاه", callback_data=f"admin:plan:edit:devices:{plan_id}"),
                InlineKeyboardButton(text="🔀 فعال/غیرفعال", callback_data=f"admin:plan:toggle:{plan_id}"),
            ],
            [
                InlineKeyboardButton(text="↑", callback_data=f"admin:plan:up:{plan_id}"),
                InlineKeyboardButton(text="↓", callback_data=f"admin:plan:down:{plan_id}"),
            ],
            [InlineKeyboardButton(text="« پلن‌ها", callback_data="admin:plans")],
        ]
    )


def _plans_list_kb(plans) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if p.is_active else '⛔'} {p.name_fa} — {p.price_toman:,}",
                callback_data=f"admin:plan:view:{p.id}",
            )
        ]
        for p in plans
    ]
    rows.append([InlineKeyboardButton(text="➕ پلن جدید", callback_data="admin:plan:create")])
    rows.append([InlineKeyboardButton(text="« فروش", callback_data="admin:hub:commerce")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:hub:commerce")
async def commerce_hub(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_callback_answer(callback, "دسترسی ندارید.", show_alert=True)
        return
    await callback.message.edit_text("🛒 <b>فروش و پلن‌ها</b>", reply_markup=commerce_hub_kb(), parse_mode="HTML")
    await safe_callback_answer(callback)


@router.callback_query(F.data == "admin:plans")
async def plans_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    items = await plan_svc.list_plans(session)
    await callback.message.edit_text(
        "📋 <b>پلن‌های VPN</b>\nروی هر پلن بزنید برای ویرایش.",
        reply_markup=_plans_list_kb(items),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:plan:view:"))
async def plan_view(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split(":")[-1])
    plan = await plan_svc.get_plan(session, plan_id)
    if not plan:
        await safe_callback_answer(callback, "پلن یافت نشد.", show_alert=True)
        return
    text = (
        f"<b>{plan.name_fa}</b>\n"
        f"slug: <code>{plan.slug}</code>\n"
        f"قیمت: <code>{plan.price_toman:,}</code> تومان\n"
        f"دستگاه: <code>{plan.device_count}</code>\n"
        f"مدت: <code>{plan.duration_days}</code> روز\n"
        f"وضعیت: {'فعال' if plan.is_active else 'غیرفعال'}"
    )
    await callback.message.edit_text(text, reply_markup=_plan_actions_kb(plan_id), parse_mode="HTML")
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:plan:toggle:"))
async def plan_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    plan_id = int(callback.data.split(":")[-1])
    plan = await plan_svc.get_plan(session, plan_id)
    if plan:
        await plan_svc.update_plan_field(
            session, plan, "is_active", not plan.is_active, callback.from_user.id
        )
        await session.commit()
    await plan_view(callback, session)


@router.callback_query(F.data.regexp(r"^admin:plan:(up|down):\d+$"))
async def plan_reorder(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    direction = parts[2]
    plan_id = int(parts[3])
    plan = await plan_svc.get_plan(session, plan_id)
    if plan:
        await plan_svc.swap_sort_order(session, plan, direction)
        await session.commit()
    await plans_list(callback, session)


@router.callback_query(F.data.startswith("admin:plan:edit:"))
async def plan_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    field = parts[3]
    plan_id = int(parts[4])
    await state.set_state(AdminStates.plan_edit_value)
    await state.update_data(plan_id=plan_id, plan_field=field)
    prompts = {"name": "نام جدید پلن:", "price": "قیمت جدید (تومان):", "devices": "تعداد دستگاه:"}
    await callback.message.edit_text(
        prompts.get(field, "مقدار جدید:"),
        reply_markup=cancel_fsm_kb(),
    )
    await safe_callback_answer(callback)


@router.message(AdminStates.plan_edit_value)
async def plan_edit_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    plan = await plan_svc.get_plan(session, data["plan_id"])
    if not plan:
        await message.answer("پلن یافت نشد.")
        await state.clear()
        return
    field = data["plan_field"]
    val = (message.text or "").strip()
    if field in {"price", "devices"} and not val.isdigit():
        await message.answer("لطفا مقدار عددی معتبر وارد کنید.")
        return
    mapping = {
        "name": ("name_fa", val),
        "price": ("price_toman", int(val) if val.isdigit() else 0),
        "devices": ("device_count", int(val) if val.isdigit() else 0),
    }
    if field not in mapping:
        await message.answer("فیلد نامعتبر.")
        return
    attr, parsed = mapping[field]
    try:
        await plan_svc.update_plan_field(session, plan, attr, parsed, message.from_user.id)
        await session.commit()
        await state.clear()
        await message.answer("✅ ذخیره شد.", reply_markup=back_to_admin_kb())
    except PlanValidationError as e:
        await message.answer(f"❌ {e}")


@router.callback_query(F.data == "admin:plan:create")
async def plan_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.plan_create)
    await state.update_data(plan_create_step="slug")
    await callback.message.edit_text(
        "slug پلن (مثلاً device_4):",
        reply_markup=cancel_fsm_kb(),
    )
    await safe_callback_answer(callback)


@router.message(AdminStates.plan_create)
async def plan_create_steps(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    step = data.get("plan_create_step")
    val = (message.text or "").strip()
    if step == "slug":
        await state.update_data(plan_slug=val, plan_create_step="name")
        await message.answer("نام فارسی پلن:", reply_markup=cancel_fsm_kb())
    elif step == "name":
        await state.update_data(plan_name=val, plan_create_step="price")
        await message.answer("قیمت (تومان):", reply_markup=cancel_fsm_kb())
    elif step == "price":
        if not val.isdigit():
            await message.answer("قیمت باید عددی باشد.")
            return
        await state.update_data(plan_price=int(val), plan_create_step="devices")
        await message.answer("تعداد دستگاه:", reply_markup=cancel_fsm_kb())
    elif step == "devices":
        if not val.isdigit():
            await message.answer("تعداد دستگاه باید عددی باشد.")
            return
        try:
            plan = await plan_svc.create_plan(
                session,
                slug=data["plan_slug"],
                name_fa=data["plan_name"],
                device_count=int(val),
                price_toman=data["plan_price"],
                admin_telegram_id=message.from_user.id,
            )
            await session.commit()
            await state.clear()
            await message.answer(f"✅ پلن {plan.name_fa} ایجاد شد.", reply_markup=back_to_admin_kb())
        except PlanValidationError as e:
            await message.answer(f"❌ {e}")


@router.callback_query(F.data == "admin:commerce:copy")
async def copy_menu(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:copy:edit:{key}")]
        for key, (_, label) in COPY_FIELDS.items()
    ]
    rows.append([InlineKeyboardButton(text="« فروش", callback_data="admin:hub:commerce")])
    await callback.message.edit_text(
        "✏️ <b>متن‌های ربات</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("admin:copy:edit:"))
async def copy_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[-1]
    await state.set_state(AdminStates.bot_copy_edit)
    await state.update_data(copy_key=key)
    label = COPY_FIELDS[key][1]
    await callback.message.edit_text(f"متن جدید برای «{label}»:", reply_markup=cancel_fsm_kb())
    await safe_callback_answer(callback)


@router.message(AdminStates.bot_copy_edit)
async def copy_edit_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    setting_key = COPY_FIELDS[data["copy_key"]][0]
    await bot_content.set_setting(session, setting_key, message.text.strip())
    await session.commit()
    await state.clear()
    await message.answer("✅ متن ذخیره شد.", reply_markup=back_to_admin_kb())
