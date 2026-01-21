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


def _send_user_arrival_notification(user_id: int, tracking: str, shipment_status: str) -> bool:
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
            "telegram send failed (user_id=%s, tracking=%s)",
            user_id,
            tracking,
        )
        return False
    return True


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
        return _send_user_arrival_notification(user_id=user_id, tracking=tracking, shipment_status=shipment_status)
    except Exception as e:
        logger.exception(
            "notify_user_arrival_task failed (user_id=%s, tracking=%s): %s",
            user_id,
            tracking,
            e,
        )
        return False


@shared_task(bind=True)
def notify_import_arrivals_task(self, group_id: int) -> dict:
    try:
        gid = int(group_id)
    except Exception:
        gid = 0

    qs = tg_models.Shipment.objects.filter(
        group_id=gid,
        import_status=tg_models.Shipment.ImportStatus.OK,
    ).exclude(user__isnull=True)

    try:
        total = int(qs.count())
    except Exception:
        total = 0

    sent = 0
    failed = 0
    if total <= 0:
        self.update_state(state="SUCCESS", meta={"current": 0, "total": 0, "sent": 0, "failed": 0})
        return {"current": 0, "total": 0, "sent": 0, "failed": 0}

    self.update_state(state="PROGRESS", meta={"current": 0, "total": total, "sent": 0, "failed": 0})

    idx = 0
    for sh in qs.only("id", "user_id", "tracking_number", "status").iterator(chunk_size=200):
        idx += 1
        ok = False
        try:
            ok = _send_user_arrival_notification(user_id=int(sh.user_id), tracking=str(sh.tracking_number), shipment_status=str(sh.status))
        except Exception:
            ok = False

        if ok:
            sent += 1
        else:
            failed += 1

        self.update_state(state="PROGRESS", meta={"current": idx, "total": total, "sent": sent, "failed": failed})

    return {"current": total, "total": total, "sent": sent, "failed": failed}
