
import time
import html
import re

import telebot
from telebot import types
from telebot import apihelper

from django.db.utils import OperationalError, ProgrammingError

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


def _onboarding_keyboard(manager_contact: str, registration_webapp_url: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()

    manager_url = _manager_url(manager_contact)
    if manager_url:
        kb.add(types.InlineKeyboardButton("Написать менеджеру", url=manager_url))
    else:
        kb.add(types.InlineKeyboardButton("Написать менеджеру", callback_data="noop"))

    registration_webapp_url = (registration_webapp_url or "").strip()
    if registration_webapp_url and _is_https_url(registration_webapp_url):
        kb.add(
            types.InlineKeyboardButton(
                "Получить код",
                web_app=types.WebAppInfo(url=registration_webapp_url),
            )
        )
    else:
        kb.add(types.InlineKeyboardButton("Получить код", callback_data="register"))
    return kb


def _main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👤 Профиль", "🎁 Адреса", "📦 Мои посылки")
    kb.row("🛒 Оптовый заказ", "⛔ Запрещенные товары", "⚙ Поддержка")
    kb.row("✅ Добавить трек")
    return kb


def _build_profile_webapp_url(settings_obj: base_models.Settings | None) -> str | None:
    if not settings_obj:
        return None
    base_url = (getattr(settings_obj, "website", "") or "").strip().rstrip("/")
    if not base_url.startswith("https://"):
        return None
    return f"{base_url}/webapp/profile/"


def start_bot(token: str) -> None:
    apihelper.CONNECT_TIMEOUT = 10
    apihelper.READ_TIMEOUT = 60

    bot = telebot.TeleBot(token)

    def _get_settings() -> base_models.Settings | None:
        try:
            return base_models.Settings.objects.first()
        except (OperationalError, ProgrammingError):
            return None

    settings_obj = _get_settings()
    if not settings_obj or not settings_obj.is_bot_enabled:
        return

    def _admin_chat_id() -> int | None:
        s = _get_settings()
        if not s:
            return None
        admin_obj = getattr(s, "admin", None)
        raw = getattr(admin_obj, "admin_id", None)
        if raw is None:
            return None
        try:
            return int(str(raw).strip())
        except ValueError:
            return None

    def _notify_admin(text: str) -> None:
        admin_chat = _admin_chat_id()
        if not admin_chat:
            return
        try:
            bot.send_message(admin_chat, text)
        except Exception:
            return

    track_state: dict[int, str] = {}

    def _get_or_create_user(message) -> tg_models.User | None:
        try:
            from_user = message.from_user
            if not from_user or not from_user.id:
                return None
            user_obj, _ = tg_models.User.objects.update_or_create(
                telegram_id=int(from_user.id),
                defaults={
                    "username": (from_user.username or ""),
                    "first_name": (from_user.first_name or ""),
                    "last_name": (from_user.last_name or ""),
                    "language_code": (getattr(from_user, "language_code", "") or ""),
                },
            )
            return user_obj
        except Exception:
            return None

    def _format_money(value) -> str:
        try:
            return f"{value:.2f}"
        except Exception:
            return str(value)

    @bot.message_handler(commands=["start"])
    def start(message):
        s = _get_settings()
        if not s or not s.is_bot_enabled:
            return

        user_obj = _get_or_create_user(message)
        if user_obj and user_obj.status == tg_models.User.Status.CLIENT_REGISTERED:
            bot.send_message(
                message.chat.id,
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
        bot.send_message(
            message.chat.id,
            greeting,
            reply_markup=_onboarding_keyboard(manager_contact, registration_webapp_url),
        )

    @bot.callback_query_handler(func=lambda c: c.data in {"register", "noop"})
    def onboarding_callback(call):
        if call.data == "noop":
            _notify_admin(
                "Системное: пользователь нажал 'Написать менеджеру', но manager_contact не настроен в Settings."
            )
            bot.answer_callback_query(call.id)
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            except Exception:
                pass
            bot.send_message(call.message.chat.id, "Контакт менеджера временно недоступен.")
            return

        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.send_message(call.message.chat.id, "Пройдите регистрацию по кнопке (WebApp).")


    @bot.message_handler(func=lambda m: m.text == "👤 Профиль")
    def profile(message):
        user_obj = _get_or_create_user(message)
        if not user_obj:
            bot.send_message(message.chat.id, "Не удалось определить пользователя.", reply_markup=_main_menu_keyboard())
            return

        code = user_obj.client_code or ""
        full_name = user_obj.full_name or ""
        phone = user_obj.phone or ""
        address = user_obj.address or ""

        s = _get_settings()
        wh = base_models.Warehouse.objects.order_by("name").first()
        pvz_city = ""
        pvz_phone_line = (getattr(wh, "phone", "") or "").strip() if wh else (getattr(s, "phone", "") or "").strip() if s else ""

        filial_obj = getattr(user_obj, "filial", None)
        manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
        manager_url = _manager_url(manager_contact)
        work_hours = (getattr(filial_obj, "work_hours", "") or "").strip() if filial_obj else ""
        pvz_location_url = (getattr(filial_obj, "pvz_location_url", "") or "").strip() if filial_obj else ""
        cabinet_url = (getattr(s, "website", "") or "").strip() if s else ""
        profile_webapp_url = _build_profile_webapp_url(s)

        lines: list[str] = [
            "📄 Ваш профиль 📄",
            "",
            f"🪪 Персональный КОД: {code}",
            f"👤 ФИО: {full_name}",
            f"📞 Номер: {phone}",
            f"🏡 Адрес: {address}",
            "",
            f"📍 ПВЗ: {pvz_city}",
            f"📍 ПВЗ телефон: {pvz_phone_line}",
            f"🕒 Часы работы: {work_hours or '—'}",
            f"🗺 Локация на Карте: {pvz_location_url or '—'}",
        ]

        kb_inline = types.InlineKeyboardMarkup()
        if profile_webapp_url:
            kb_inline.add(
                types.InlineKeyboardButton(
                    "Открыть профиль",
                    web_app=types.WebAppInfo(url=profile_webapp_url),
                )
            )
        if manager_url:
            kb_inline.add(types.InlineKeyboardButton("WhatsApp менеджера", url=manager_url))

        text = "\n".join(lines).strip()
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=kb_inline if kb_inline.keyboard else None,
            disable_web_page_preview=True,
        )

    @bot.message_handler(func=lambda m: m.text == "📦 Мои посылки")
    def my_parcels(message):
        user_obj = _get_or_create_user(message)
        if not user_obj:
            bot.send_message(message.chat.id, "Не удалось определить пользователя.", reply_markup=_main_menu_keyboard())
            return

        qs = tg_models.Shipment.objects.filter(user=user_obj).order_by("-created_at")
        if not qs.exists():
            bot.send_message(
                message.chat.id,
                "У вас активных посылок нет.",
                reply_markup=_main_menu_keyboard(),
            )
            return

        lines: list[str] = []
        for sh in qs[:15]:
            lines.append(
                (
                    f"📦 {sh.tracking_number}\n"
                    f"Статус: {sh.get_status_display()}\n"
                    f"Вес: {sh.weight_kg} кг\n"
                    f"Сумма: {_format_money(sh.total_price)}\n"
                )
            )
        bot.send_message(message.chat.id, "Мои посылки:\n\n" + "\n".join(lines), reply_markup=_main_menu_keyboard())

    @bot.message_handler(func=lambda m: m.text == "🎁 Адреса")
    def warehouses(message):
        user_obj = _get_or_create_user(message)
        if not user_obj:
            bot.send_message(
                message.chat.id,
                "Не удалось определить пользователя.",
                reply_markup=_main_menu_keyboard()
            )
            return

        s = _get_settings()
        filial_obj = getattr(user_obj, "filial", None)
        manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
        manager_url = _manager_url(manager_contact)
        manager_phone = (getattr(s, "phone", "") or "").strip() if s else ""

        wh = base_models.Warehouse.objects.order_by("name").first()
        china_address = (getattr(wh, "address", "") or "").strip() if wh else ""

        wh_phone = (getattr(wh, "phone", "") or "").strip() if wh else (getattr(s, "phone", "") or "").strip() if s else ""

        code_value = (user_obj.client_code or "—").strip()
        address_value = (china_address or "—").strip()

        copy_lines = "\n".join([
            f"阿{code_value}",
            wh_phone or "—",
            f"{address_value}{code_value}",
        ])

        bot.send_message(
            message.chat.id,
            f"`{copy_lines}`",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

        # 3️⃣ Предупреждение + WhatsApp
        warning_text = (
            "✅ *Важно*\n\n"
            "Чтобы ваши посылки не потерялись, обязательно отправьте менеджеру *скрин* "
            "заполненного адреса и получите *подтверждение* ✅\n\n"
            f"📱 *Телефон*: {manager_phone or '—'}\n\n"
            "❗❗❗ Только после подтверждения ✅ адреса Карго несет ответственность за ваши посылки 📦"
        )

        kb_inline = types.InlineKeyboardMarkup()
        if manager_url:
            kb_inline.add(types.InlineKeyboardButton("WhatsApp менеджера", url=manager_url))

        bot.send_message(
            message.chat.id,
            warning_text,
            reply_markup=kb_inline if kb_inline.keyboard else None,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )


    @bot.message_handler(func=lambda m: m.text == "🛒 Оптовый заказ")
    def wholesale_order(message):
        user_obj = _get_or_create_user(message)
        filial_obj = getattr(user_obj, "filial", None) if user_obj else None
        raw = (getattr(filial_obj, "wholesale_order_text", "") or "") if filial_obj else ""
        text = _html_to_text(str(raw))
        if not text:
            text = "Оптовый заказ: пока не заполнено."
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=_main_menu_keyboard(),
            disable_web_page_preview=True,
        )

    @bot.message_handler(func=lambda m: m.text == "⛔ Запрещенные товары")
    def prohibited(message):
        s = _get_settings()
        raw = (getattr(s, "prohibited_goods_text", "") or "") if s else ""
        text = _html_to_text(str(raw))
        if not text:
            text = "Запрещённые товары: пока не заполнено."
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=_main_menu_keyboard(),
            disable_web_page_preview=True,
        )

    @bot.message_handler(func=lambda m: m.text == "⚙ Поддержка")
    def support(message):
        s = _get_settings()
        if not s:
            bot.send_message(message.chat.id, "Поддержка временно недоступна.", reply_markup=_main_menu_keyboard())
            return

        user_obj = _get_or_create_user(message)
        filial_obj = getattr(user_obj, "filial", None) if user_obj else None

        manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
        manager_url = _manager_url(manager_contact)

        instagram_url = (getattr(filial_obj, "instagram_url", "") or "").strip() if filial_obj else ""
        work_hours = (getattr(filial_obj, "work_hours", "") or "").strip() if filial_obj else ""
        pvz_location_url = (getattr(filial_obj, "pvz_location_url", "") or "").strip() if filial_obj else ""

        pvz_title = ""
        pvz_address = ""
        pvz_phone = ""
        if filial_obj:
            city = (getattr(filial_obj, "city", "") or "").strip()
            name = (getattr(filial_obj, "name", "") or "").strip()
            pvz_title = " — ".join([v for v in [city, name] if v]).strip(" —")
            pvz_address = (getattr(filial_obj, "address", "") or "").strip()
            pvz_phone = (manager_contact or "").strip()
        else:
            wh = base_models.Warehouse.objects.order_by("name").first()
            pvz_title = (getattr(wh, "name", "") or "").strip() if wh else ""
            pvz_address = (getattr(wh, "address", "") or "").strip() if wh else ""
            pvz_phone = (getattr(wh, "phone", "") or "").strip() if wh else (getattr(s, "phone", "") or "").strip()

        lines: list[str] = [
            "Если у вас есть вопросы? Напишите нам",
            "",
            f"📍 ПВЗ: {pvz_title or '—'}",
            f"🏢 Адрес ПВЗ: {pvz_address or '—'}" if (pvz_address or "").strip() else "",
            f"📞 Телефон менеджера: {pvz_phone or '—'}",
            f"🔗 WhatsApp: {manager_url}" if manager_url else "",
            f"🕒 Часы работы: {work_hours or '—'}",
            "🗺 Локация на Карте:",
        ]
        text = "\n".join([ln for ln in lines if ln]).strip()

        kb = types.InlineKeyboardMarkup()
        if manager_url:
            kb.add(types.InlineKeyboardButton("Написать на WhatsApp", url=manager_url))
        if pvz_location_url and pvz_location_url.startswith("http"):
            kb.add(types.InlineKeyboardButton("Локация на карте", url=pvz_location_url))
        if instagram_url and instagram_url.startswith("http"):
            kb.add(types.InlineKeyboardButton("Наш instagram", url=instagram_url))

        bot.send_message(
            message.chat.id,
            text,
            reply_markup=kb if kb.keyboard else None,
            disable_web_page_preview=True,
        )

    @bot.message_handler(func=lambda m: m.text == "✅ Добавить трек")
    def add_track(message):
        user_obj = _get_or_create_user(message)
        if not user_obj:
            bot.send_message(message.chat.id, "Не удалось определить пользователя.", reply_markup=_main_menu_keyboard())
            return
        track_state[message.chat.id] = "waiting_tracking"
        bot.send_message(
            message.chat.id,
            "Отправьте трек-номер сообщением (например: LP123456789CN).",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: track_state.get(m.chat.id) == "waiting_tracking", content_types=["text"])
    def add_track_submit(message):
        tracking = (message.text or "").strip()
        if not tracking or tracking.startswith("/"):
            return

        track_state.pop(message.chat.id, None)
        user_obj = _get_or_create_user(message)
        if not user_obj:
            bot.send_message(message.chat.id, "Не удалось определить пользователя.", reply_markup=_main_menu_keyboard())
            return

        _, created = tg_models.Shipment.objects.get_or_create(
            user=user_obj,
            tracking_number=tracking,
            defaults={"status": tg_models.Shipment.Status.CREATED},
        )
        if created:
            bot.send_message(
                message.chat.id,
                "Трек добавлен ✅\n\nОператор проверит и добавит данные по весу/стоимости.",
                reply_markup=_main_menu_keyboard(),
            )
            return

        bot.send_message(
            message.chat.id,
            "Этот трек уже добавлен ранее.",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(content_types=["text"])
    def fallback(message):
        if track_state.get(message.chat.id) == "waiting_tracking":
            return
        bot.send_message(
            message.chat.id,
            "Выберите пункт меню:",
            reply_markup=_main_menu_keyboard(),
        )

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=30)
        except Exception:
            time.sleep(5)
