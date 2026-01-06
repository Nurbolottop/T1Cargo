import os

import telebot
from telebot import types


def _onboarding_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Написать менеджеру", "Пройти регистрацию")
    return kb


def _main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👤 Профиль", "🎁 Адреса", "📦 Мои посылки")
    kb.row("📕 Инструкция", "⛔ Запрещенные товары", "⚙ Поддержка")
    kb.row("✅ Добавить трек")
    return kb


def start_bot(token: str) -> None:
    bot = telebot.TeleBot(token)

    company_name = os.getenv("COMPANY_NAME", "Dragon Express 777 Osh")
    manager_contact = os.getenv("MANAGER_CONTACT", "")

    registration_state: dict[int, str] = {}

    @bot.message_handler(commands=["start"])
    def start(message):
        greeting = (
            "Пройдите регистрацию\n\n"
            f"Привет! Я чат-бот карго-компании {company_name}.\n\n"
            "Я помогу вам получить персональный код и правильно заполнить адрес склада в Китае 🇨🇳\n\n"
            f"С уважением, команда {company_name}🧡"
        )
        bot.send_message(message.chat.id, greeting, reply_markup=_onboarding_keyboard())
        bot.send_message(
            message.chat.id,
            "Пройдите регистрацию для получения нового КОДА",
            reply_markup=_onboarding_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "Написать менеджеру")
    def write_manager(message):
        if manager_contact:
            bot.send_message(
                message.chat.id,
                f"Связь с менеджером: {manager_contact}",
                reply_markup=_onboarding_keyboard(),
            )
            return

        bot.send_message(
            message.chat.id,
            "Контакт менеджера пока не настроен. Укажи MANAGER_CONTACT в .env (например @username или +996...).",
            reply_markup=_onboarding_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "Пройти регистрацию")
    def register_start(message):
        registration_state[message.chat.id] = "waiting_phone"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        btn = types.KeyboardButton("Отправить номер телефона", request_contact=True)
        kb.row(btn)
        bot.send_message(
            message.chat.id,
            "Отправьте ваш номер телефона (кнопкой ниже или текстом), чтобы мы выдали персональный код.",
            reply_markup=kb,
        )

    @bot.message_handler(content_types=["contact"])
    def register_contact(message):
        if registration_state.get(message.chat.id) != "waiting_phone":
            return

        phone = message.contact.phone_number
        registration_state.pop(message.chat.id, None)
        bot.send_message(
            message.chat.id,
            f"Спасибо! Телефон получен: {phone}\n\nВаш персональный код будет выдан менеджером.",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: registration_state.get(m.chat.id) == "waiting_phone")
    def register_phone_text(message):
        phone = (message.text or "").strip()
        if not phone:
            return
        registration_state.pop(message.chat.id, None)
        bot.send_message(
            message.chat.id,
            f"Спасибо! Телефон получен: {phone}\n\nВаш персональный код будет выдан менеджером.",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "👤 Профиль")
    def profile(message):
        bot.send_message(
            message.chat.id,
            "Профиль клиента:\n\nФИО: —\nТелефон: —\nTelegram ID: —\nОбщий долг: —\nАктивных заказов: —",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "📦 Мои посылки")
    def my_parcels(message):
        bot.send_message(
            message.chat.id,
            "Мои посылки: пока пусто.\n\nКогда оператор добавит заказ в CRM, он появится здесь.",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "🎁 Адреса")
    def warehouses(message):
        bot.send_message(
            message.chat.id,
            "Адрес склада (Китай):\n—\n\nИнструкция по заполнению адреса в Pinduoduo:\n—",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "📕 Инструкция")
    def instruction(message):
        bot.send_message(
            message.chat.id,
            "Инструкция:\n1) Как заказать с Pinduoduo\n2) Как указать адрес карго\n3) Как считается доставка\n4) Когда и как производится оплата",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "⛔ Запрещенные товары")
    def prohibited(message):
        bot.send_message(
            message.chat.id,
            "Запрещённые товары:\n—\n\nВнимание: возможны штрафы/конфискация.",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "⚙ Поддержка")
    def support(message):
        bot.send_message(
            message.chat.id,
            "Поддержка:\n—\n\nНапишите ваш вопрос в чат.",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == "✅ Добавить трек")
    def add_track(message):
        bot.send_message(
            message.chat.id,
            "Отправьте трек-номер сообщением.",
            reply_markup=_main_menu_keyboard(),
        )

    @bot.message_handler(content_types=["text"])
    def fallback(message):
        bot.send_message(
            message.chat.id,
            "Выберите пункт меню:",
            reply_markup=_main_menu_keyboard(),
        )

    bot.infinity_polling(skip_pending=True)
