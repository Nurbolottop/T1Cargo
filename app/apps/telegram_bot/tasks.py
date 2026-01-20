import logging

from celery import shared_task

from apps.base import models as base_models
from apps.telegram_bot import models as tg_models
from apps.telegram_bot.views import _send_telegram_message

logger = logging.getLogger(__name__)


def _shipment_notify_text_in_transit(tracking: str) -> str:
    tracking = (tracking or "—").strip() or "—"
    return (
        "📦✨ Ваш товар отправлен из Китая!\n\n"
        f"🧾 Трек-номер: {tracking}\n\n"
        "🚚 Посылка выехала со склада в Китае\n"
        "и направляется в Кыргызстан KG\n\n"
        "🔔 Мы уведомим вас, как только товар прибудет."
    )


def _shipment_notify_text_bishkek(tracking: str) -> str:
    tracking = (tracking or "—").strip() or "—"
    return (
        "📦📍 Отличные новости!\n\n"
        "Ваш товар прибыл в Бишкек KG\n\n"
        f"🧾 Трек-номер: {tracking}\n\n"
        "🛠 Сейчас посылка проходит оформление\n"
        "и подготовку к выдаче.\n\n"
        "🔔 Скоро отправим сообщение о готовности."
    )


def _shipment_notify_text_ready_for_pickup(tracking: str, weight_kg=None, total_price=None) -> str:
    tracking = (tracking or "—").strip() or "—"

    weight_line = ""
    price_line = ""
    if weight_kg is not None and str(weight_kg).strip() != "":
        weight_line = f"⚖️ Вес: {weight_kg} кг\n"
    if total_price is not None and str(total_price).strip() != "":
        price_line = f"💰 Стоимость доставки: {total_price} сом\n"

    return (
        "✅📦 Посылка готова к выдаче!\n\n"
        f"🧾 Трек-номер: {tracking}\n"
        f"{weight_line}"
        f"{price_line}\n"
        "🆓 Бесплатное хранение — 3 дня\n"
        "⏳ Далее начисляется плата за хранение.\n\n"
        "📍 Вы можете забрать посылку в пункте выдачи."
    )


@shared_task
def notify_user_arrival_task(user_id: int, tracking: str, shipment_status: str) -> bool:
    try:
        token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
        if not token:
            return False

        user_obj = tg_models.User.objects.filter(id=user_id).first()
        if user_obj is None:
            return False

        chat_id = getattr(user_obj, "telegram_id", None)
        if not chat_id:
            return False

        if shipment_status == tg_models.Shipment.Status.WAREHOUSE:
            text = _shipment_notify_text_ready_for_pickup(tracking=tracking)
        elif shipment_status == tg_models.Shipment.Status.ON_THE_WAY:
            text = _shipment_notify_text_in_transit(tracking=tracking)
        else:
            text = _shipment_notify_text_bishkek(tracking=tracking)

        ok = _send_telegram_message(token=token, chat_id=int(chat_id), text=text)
        if not ok:
            logger.exception(
                "notify_user_arrival_task: telegram send failed (user_id=%s, tracking=%s)",
                user_id,
                tracking,
            )
            return False

        return True
    except Exception as e:
        logger.exception(
            "notify_user_arrival_task failed (user_id=%s, tracking=%s): %s",
            user_id,
            tracking,
            e,
        )
        return False
