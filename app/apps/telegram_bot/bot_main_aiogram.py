import asyncio
import html
import re
import time
import traceback
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.db.utils import OperationalError, ProgrammingError

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from apps.base import models as base_models
from apps.telegram_bot import models as tg_models


def _is_https_url(url: str) -> bool:
    value = (url or "").strip().lower()
    return value.startswith("https://")


def _manager_url(manager_contact: str) -> str | None:
    value = (manager_contact or "").strip()
    if not value:
        return None

    if value.startswith("http://") or value.startswith("https://"):
        return value

    if value.startswith("@"):  # telegram
        username = value[1:]
        if username:
            return f"https://t.me/{username}"
        return None

    normalized = "".join(ch for ch in value if ch.isdigit())
    if normalized:
        return f"https://wa.me/{normalized}"

    return None


def _html_to_text(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""

    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*p\s*>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*p\b[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _onboarding_keyboard(manager_contact: str, registration_webapp_url: str) -> InlineKeyboardMarkup:
    registration_webapp_url = (registration_webapp_url or "").strip()
    if registration_webapp_url and _is_https_url(registration_webapp_url):
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Получить код", web_app=WebAppInfo(url=registration_webapp_url))]]
        )
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Получить код", callback_data="register")]])


def _main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎁 Адреса"), KeyboardButton(text="📦 Мои посылки")],
            [KeyboardButton(text="📊 График"), KeyboardButton(text="⛔ Запрещенные товары"), KeyboardButton(text="⚙ Поддержка")],
            [KeyboardButton(text="🛒 Расчет оптовых товаров")],
        ],
        resize_keyboard=True,
    )


def _build_profile_webapp_url(settings_obj: base_models.Settings | None) -> str | None:
    if not settings_obj:
        return None
    base_url = (getattr(settings_obj, "website", "") or "").strip().rstrip("/")
    if not base_url.startswith("https://"):
        return None
    return f"{base_url}/webapp/profile/"


def start_bot(token: str) -> None:
    while True:
        try:
            asyncio.run(_run_bot(token))
            return
        except KeyboardInterrupt:
            return
        except Exception:
            traceback.print_exc()
            time.sleep(5)


def _get_settings_sync() -> base_models.Settings | None:
    try:
        return base_models.Settings.objects.first()
    except (OperationalError, ProgrammingError):
        return None


async def _get_settings() -> base_models.Settings | None:
    return await sync_to_async(_get_settings_sync, thread_sensitive=True)()


def _is_registered(user_obj: tg_models.User | None) -> bool:
    if not user_obj:
        return False
    if getattr(user_obj, "status", None) != tg_models.User.Status.CLIENT_REGISTERED:
        return False
    return bool((getattr(user_obj, "client_code", None) or "").strip())


async def _get_or_create_user(message: Message) -> tg_models.User | None:
    try:
        from_user = getattr(message, "from_user", None)
        if not from_user or not getattr(from_user, "id", None):
            return None

        def _sync_op() -> tg_models.User | None:
            defaults = {
                "first_name": (from_user.first_name or ""),
                "last_name": (from_user.last_name or ""),
                "language_code": (getattr(from_user, "language_code", "") or ""),
            }
            if from_user.username:
                defaults["username"] = from_user.username

            user_obj, _ = tg_models.User.objects.update_or_create(
                telegram_id=int(from_user.id),
                defaults=defaults,
            )

            if not (getattr(user_obj, "full_name", "") or "").strip():
                first = (from_user.first_name or "").strip()
                last = (from_user.last_name or "").strip()
                tg_name = " ".join([v for v in [first, last] if v]).strip()
                if not tg_name:
                    tg_name = (from_user.username or "").strip()
                if tg_name:
                    user_obj.full_name = tg_name
                    user_obj.save(update_fields=["full_name", "updated_at"])

            return tg_models.User.objects.select_related("filial").filter(id=user_obj.id).first()

        return await sync_to_async(_sync_op, thread_sensitive=True)()
    except Exception:
        return None


def _format_money(value) -> str:
    try:
        return f"{value:.2f}"
    except Exception:
        return str(value)


def _format_weight(value) -> str:
    try:
        s = f"{value:.3f}"
    except Exception:
        return str(value)
    s = s.rstrip("0").rstrip(".")
    return s or "0"


def _format_date_ru(d) -> str:
    if not d:
        return "—"
    try:
        return d.strftime("%d.%m.%Y")
    except Exception:
        return str(d)


async def _send_registration_required(bot: Bot, chat_id: int) -> None:
    s = await _get_settings()
    if not s or not s.is_bot_enabled:
        return
    registration_webapp_url = getattr(s, "registration_webapp_url", "")
    await bot.send_message(
        chat_id,
        "Сначала пройдите регистрацию по кнопке ниже.",
        reply_markup=_onboarding_keyboard(s.phone, registration_webapp_url),
    )


async def _run_bot(token: str) -> None:
    settings_obj = await _get_settings()
    if not settings_obj or not settings_obj.is_bot_enabled:
        return

    session = AiohttpSession(timeout=90)
    bot = Bot(token=token, session=session)
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        s = await _get_settings()
        if not s or not s.is_bot_enabled:
            return

        user_obj = await _get_or_create_user(message)
        if user_obj and user_obj.status == tg_models.User.Status.CLIENT_REGISTERED:
            await message.answer(
                "Привет! Спасибо что подписался",
                reply_markup=_main_menu_keyboard(),
            )
            return

        company_name = s.title
        manager_contact = s.phone
        registration_webapp_url = getattr(s, "registration_webapp_url", "")
        greeting = (
            "Пройдите регистрацию\n\n"
            f"Привет! Я чат-бот карго-компании {company_name}.\n\n"
            "Я помогу вам получить персональный код и правильно заполнить адрес склада в Китае 🇨🇳\n\n"
            f"С уважением, команда {company_name}🧡\n\n"
            "Пройдите регистрацию для получения нового КОДА"
        )
        await message.answer(
            greeting,
            reply_markup=_onboarding_keyboard(manager_contact, registration_webapp_url),
        )

    @router.callback_query(F.data == "register")
    async def onboarding_callback(call: CallbackQuery) -> None:
        try:
            await call.answer()
        except Exception:
            pass
        try:
            if call.message is not None:
                await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            if call.message is not None:
                await bot.send_message(call.message.chat.id, "Пройдите регистрацию по кнопке (WebApp).")
        except Exception:
            pass

    @router.message(F.text == "👤 Профиль")
    async def profile(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not user_obj:
            await message.answer("Не удалось определить пользователя.", reply_markup=_main_menu_keyboard())
            return
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return

        code = user_obj.client_code or ""
        full_name = user_obj.full_name or ""
        phone = user_obj.phone or ""
        address = user_obj.address or ""

        s = await _get_settings()
        filial_obj = getattr(user_obj, "filial", None)
        manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
        pvz_location_url = (getattr(filial_obj, "pvz_location_url", "") or "").strip() if filial_obj else ""
        manager_url = _manager_url(manager_contact)
        profile_webapp_url = _build_profile_webapp_url(s)

        lines: list[str] = [
            "📄 Ваш профиль 📄",
            "",
            f"🪪 Персональный КОД: {code}",
            f"👤 ФИО: {full_name}",
            f"📞 Номер: {phone}",
            f"🏡 Адрес: {address}",
            "",
            f"🗺 Локация на Карте: {pvz_location_url or '—'}",
        ]

        kb_inline_rows: list[list[InlineKeyboardButton]] = []
        if profile_webapp_url:
            kb_inline_rows.append([InlineKeyboardButton(text="Открыть профиль", web_app=WebAppInfo(url=profile_webapp_url))])
        if manager_url:
            kb_inline_rows.append([InlineKeyboardButton(text="WhatsApp менеджера", url=manager_url)])

        kb_inline = InlineKeyboardMarkup(inline_keyboard=kb_inline_rows) if kb_inline_rows else None

        text = "\n".join(lines).strip()
        await message.answer(
            text,
            reply_markup=kb_inline,
            disable_web_page_preview=True,
        )

    @router.message(F.text == "📦 Мои посылки")
    async def my_parcels(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not user_obj:
            await message.answer("Не удалось определить пользователя.", reply_markup=_main_menu_keyboard())
            return
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return

        def _sync_list_shipments() -> list[tg_models.Shipment]:
            return list(
                tg_models.Shipment.objects.select_related("group")
                .filter(user=user_obj)
                .exclude(status="issued")
                .order_by("-created_at")[:30]
            )

        items = await sync_to_async(_sync_list_shipments, thread_sensitive=True)()
        if not items:
            await message.answer("У вас активных посылок нет.", reply_markup=_main_menu_keyboard())
            return

        grouped: dict[int | None, dict] = {}
        order: list[int | None] = []

        total_weight = Decimal("0")
        total_sum = Decimal("0")

        for sh in items:
            group_obj = getattr(sh, "group", None)
            gid = getattr(group_obj, "id", None) if group_obj else None
            if gid not in grouped:
                grouped[gid] = {"group": group_obj, "items": [], "weight": Decimal("0"), "sum": Decimal("0")}
                order.append(gid)

            try:
                w = Decimal(str(getattr(sh, "weight_kg", 0) or 0))
            except Exception:
                w = Decimal("0")
            try:
                p = Decimal(str(getattr(sh, "total_price", 0) or 0))
            except Exception:
                p = Decimal("0")

            grouped[gid]["items"].append(sh)
            grouped[gid]["weight"] += w
            grouped[gid]["sum"] += p
            total_weight += w
            total_sum += p

        blocks: list[str] = []
        for gid in order:
            payload = grouped[gid]
            group_obj = payload.get("group")

            sent_date = getattr(group_obj, "sent_date", None) if group_obj else None
            group_name = (getattr(group_obj, "name", "") or "").strip() if group_obj else ""

            header = f"📅 Отправка: {_format_date_ru(sent_date)}"
            if group_name:
                header += f" | Партия: {group_name}"

            header_html = f"<b>📦 Отправка: {_format_date_ru(sent_date)}</b>"
            if group_name:
                header_html += f"\n<i>Партия:</i> {html.escape(group_name)}"

            lines_html: list[str] = [header_html]
            for sh in payload.get("items") or []:
                tracking = html.escape(str(getattr(sh, "tracking_number", "") or "—"))
                status = html.escape(str(sh.get_status_display() or "—"))
                weight = _format_weight(getattr(sh, "weight_kg", 0) or 0)
                price = _format_money(getattr(sh, "total_price", 0) or 0)
                lines_html.append(f"• <code>{tracking}</code> — <b>{status}</b>\n  ⚖️ {weight} кг   💰 {price} сом")

            group_cnt = len(payload.get("items") or [])
            group_weight = _format_weight(payload.get("weight") or 0)
            group_sum = _format_money(payload.get("sum") or 0)
            lines_html.append(f"➡️ <b>Итого по партии:</b> {group_cnt} шт • {group_weight} кг • {group_sum} сом")
            blocks.append("\n".join(lines_html))

        total_weight_s = _format_weight(total_weight)
        total_sum_s = _format_money(total_sum)
        text = (
            "<b>📦 Мои посылки</b>\n"
            "<i>Сгруппировано по партиям (датам отправки).</i>\n\n"
            + "\n\n━━━━━━━━━━━━\n\n".join(blocks)
            + "\n\n✅ <b>Общий итог:</b> "
            + f"{len(items)} шт • {total_weight_s} кг • {total_sum_s} сом"
        )
        await message.answer(
            text,
            reply_markup=_main_menu_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    @router.message(F.text == "🎁 Адреса")
    async def warehouses(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not user_obj:
            await message.answer("Не удалось определить пользователя.", reply_markup=_main_menu_keyboard())
            return
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return

        s = await _get_settings()
        filial_obj = getattr(user_obj, "filial", None)
        manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
        manager_url = _manager_url(manager_contact)
        manager_phone = manager_contact
        if not manager_phone:
            manager_phone = (getattr(s, "phone", "") or "").strip() if s else ""

        china_address = (getattr(filial_obj, "china_warehouse_address", "") or "").strip() if filial_obj else ""
        wh_phone = (getattr(filial_obj, "china_warehouse_phone", "") or "").strip() if filial_obj else ""
        if not wh_phone:
            wh_phone = (getattr(s, "phone", "") or "").strip() if s else ""

        code_value = (user_obj.client_code or "—").strip()
        address_value = (china_address or "—").strip()

        china_prefix = (getattr(filial_obj, "china_client_code_prefix", "") or "").strip() if filial_obj else ""
        if not china_prefix:
            china_prefix = "阿"

        client_phone_digits = "".join(ch for ch in (getattr(user_obj, "phone", "") or "") if ch.isdigit())
        client_phone_suffix = f" ({client_phone_digits})" if client_phone_digits else ""

        copy_lines = "\n".join(
            [
                f"{china_prefix}{code_value}",
                wh_phone or "—",
                f"{address_value}{code_value}{client_phone_suffix}",
            ]
        )

        await message.answer(
            f"`{copy_lines}`",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

        warning_text = (
            "✅ *Важно*\n\n"
            "Чтобы ваши посылки не потерялись, обязательно отправьте менеджеру *скрин* "
            "заполненного адреса и получите *подтверждение* ✅\n\n"
            f"📱 *Телефон*: {manager_phone or '—'}\n\n"
            "❗❗❗ Только после подтверждения ✅ адреса Карго несет ответственность за ваши посылки 📦"
        )

        kb_rows: list[list[InlineKeyboardButton]] = []
        if manager_url:
            kb_rows.append([InlineKeyboardButton(text="WhatsApp менеджера", url=manager_url)])
        kb_inline = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

        await message.answer(
            warning_text,
            reply_markup=kb_inline,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    @router.message(F.text.in_({"🛒 Расчет оптовых товаров", "🛒 Оптовые товары"}))
    async def wholesale_order(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return

        filial_obj = getattr(user_obj, "filial", None) if user_obj else None
        raw = (getattr(filial_obj, "wholesale_order_text", "") or "") if filial_obj else ""
        text = _html_to_text(str(raw))
        if not text:
            text = "Оптовые товары: пока не заполнено."

        whatsapp_phone_raw = (getattr(filial_obj, "wholesale_whatsapp_phone", "") or "").strip() if filial_obj else ""
        whatsapp_digits = "".join([ch for ch in whatsapp_phone_raw if ch.isdigit()])

        kb_rows: list[list[InlineKeyboardButton]] = []
        if whatsapp_digits:
            kb_rows.append([InlineKeyboardButton(text="🟢 Whatsapp номер", url=f"https://wa.me/{whatsapp_digits}")])
        kb_inline = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

        await message.answer(
            text,
            reply_markup=kb_inline if kb_inline is not None else _main_menu_keyboard(),
            disable_web_page_preview=True,
        )

    @router.message(F.text == "📊 График")
    async def schedule(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return

        filial_obj = getattr(user_obj, "filial", None) if user_obj else None
        if not filial_obj:
            s = await _get_settings()
            await message.answer(
                "Филиал не выбран. Пройдите регистрацию и выберите филиал.",
                reply_markup=_onboarding_keyboard("", getattr(s, "registration_webapp_url", "") if s else ""),
            )
            return

        city = (getattr(filial_obj, "city", "") or "").strip()
        name = (getattr(filial_obj, "name", "") or "").strip()
        pvz_title = " — ".join([v for v in [city, name] if v]).strip(" —")

        raw_hours = (getattr(filial_obj, "work_hours", "") or "")
        work_hours = _html_to_text(str(raw_hours))
        address = (getattr(filial_obj, "address", "") or "").strip()
        pvz_location_url = (getattr(filial_obj, "pvz_location_url", "") or "").strip()

        lines: list[str] = [
            "📊 График",
            "",
            f"📍 ПВЗ: {pvz_title or '—'}",
        ]
        if work_hours:
            lines.extend(["", work_hours])
        else:
            lines.append("🕒 Часы работы: —")
        if address:
            lines.append(f"🏢 Адрес: {address}")
        if pvz_location_url:
            lines.append(f"🗺 Локация: {pvz_location_url}")

        kb_rows: list[list[InlineKeyboardButton]] = []
        if pvz_location_url and pvz_location_url.startswith("http"):
            kb_rows.append([InlineKeyboardButton(text="Локация на карте", url=pvz_location_url)])
        kb_inline = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

        await message.answer(
            "\n".join(lines).strip(),
            reply_markup=kb_inline if kb_inline is not None else _main_menu_keyboard(),
            disable_web_page_preview=True,
        )

    @router.message(F.text == "⛔ Запрещенные товары")
    async def prohibited(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return
        s = await _get_settings()
        raw = (getattr(s, "prohibited_goods_text", "") or "") if s else ""
        text = _html_to_text(str(raw))
        if not text:
            text = "Запрещённые товары: пока не заполнено."
        await message.answer(
            text,
            reply_markup=_main_menu_keyboard(),
            disable_web_page_preview=True,
        )

    @router.message(F.text == "⚙ Поддержка")
    async def support(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return
        s = await _get_settings()
        if not s:
            await message.answer("Поддержка временно недоступна.", reply_markup=_main_menu_keyboard())
            return

        filial_obj = getattr(user_obj, "filial", None) if user_obj else None
        if not filial_obj:
            await message.answer(
                "Чтобы увидеть контакты вашего ПВЗ, пожалуйста, пройдите регистрацию и выберите филиал.",
                reply_markup=_onboarding_keyboard(getattr(s, "phone", ""), getattr(s, "registration_webapp_url", "")),
            )
            return

        manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
        manager_url = _manager_url(manager_contact)

        instagram_url = (getattr(filial_obj, "instagram_url", "") or "").strip() if filial_obj else ""
        pvz_location_url = (getattr(filial_obj, "pvz_location_url", "") or "").strip() if filial_obj else ""

        city = (getattr(filial_obj, "city", "") or "").strip()
        pvz_title = " — ".join([v for v in [city] if v]).strip(" —")
        pvz_address = (getattr(filial_obj, "address", "") or "").strip()
        pvz_phone = (manager_contact or "").strip()

        lines: list[str] = [
            "Если у вас есть вопросы? Напишите нам",
            "",
            f"📍 Филиал: {pvz_title or '—'}",
            f"🏢 Адрес: {pvz_address or '—'}" if (pvz_address or "").strip() else "",
            f"📞 Телефон менеджера: {pvz_phone or '—'}",
            "🗺 Локация на Карте:",
        ]
        text = "\n".join([ln for ln in lines if ln]).strip()

        kb_rows: list[list[InlineKeyboardButton]] = []
        if manager_url:
            kb_rows.append([InlineKeyboardButton(text="Написать на WhatsApp", url=manager_url)])
        if pvz_location_url and pvz_location_url.startswith("http"):
            kb_rows.append([InlineKeyboardButton(text="Локация на карте", url=pvz_location_url)])
        if instagram_url and instagram_url.startswith("http"):
            kb_rows.append([InlineKeyboardButton(text="Наш instagram", url=instagram_url)])
        kb_inline = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

        await message.answer(
            text,
            reply_markup=kb_inline,
            disable_web_page_preview=True,
        )

    @router.message(F.content_type == "text")
    async def fallback(message: Message) -> None:
        user_obj = await _get_or_create_user(message)
        if not _is_registered(user_obj):
            await _send_registration_required(bot, message.chat.id)
            return
        await message.answer("Выберите пункт меню:", reply_markup=_main_menu_keyboard())

    dp.include_router(router)

    try:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass

        await dp.start_polling(bot, polling_timeout=30)
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass
