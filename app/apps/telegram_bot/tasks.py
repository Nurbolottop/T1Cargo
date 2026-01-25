import logging

from celery import shared_task

from typing import Optional

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


def _shipment_notify_text_in_transit_batch(trackings: list[str]) -> str:
    lines = []
    for t in trackings:
        t = (t or "—").strip() or "—"
        lines.append(f"• {t}")
    list_block = "\n".join(lines) if lines else "—"
    return (
        "📦✨ Ваш товар отправлен из Китая!\n\n"
        "🧾 Трек-номера:\n"
        f"{list_block}\n\n"
        "🚚 Посылка выехала со склада в Китае\n"
        "и направляется в Кыргызстан KG\n\n"
        "🔔 Мы уведомим вас, как только товар прибудет."
    )


def _shipment_notify_text_bishkek_batch(trackings: list[str]) -> str:
    lines = []
    for t in trackings:
        t = (t or "—").strip() or "—"
        lines.append(f"• {t}")
    list_block = "\n".join(lines) if lines else "—"
    return (
        "📦📍 Отличные новости!\n\n"
        "Ваш товар прибыл в Бишкек KG\n\n"
        "🧾 Трек-номера:\n"
        f"{list_block}\n\n"
        "🛠 Сейчас посылка проходит оформление\n"
        "и подготовку к выдаче.\n\n"
        "🔔 Скоро отправим сообщение о готовности."
    )


def _shipment_notify_text_ready_for_pickup_batch(items: list[dict]) -> str:
    lines = []
    for it in items:
        t = (str(it.get("tracking") or "—")).strip() or "—"
        w = it.get("weight_kg")
        p = it.get("total_price")
        extra = []
        if w is not None and str(w).strip() != "":
            extra.append(f"{w} кг")
        if p is not None and str(p).strip() != "":
            extra.append(f"{p} сом")
        suffix = (" — " + ", ".join(extra)) if extra else ""
        lines.append(f"• {t}{suffix}")
    list_block = "\n".join(lines) if lines else "—"
    return (
        "✅📦 Посылка готова к выдаче!\n\n"
        "🧾 Трек-номера:\n"
        f"{list_block}\n\n"
        "🆓 Бесплатное хранение — 3 дня\n"
        "⏳ Далее начисляется плата за хранение.\n\n"
        "📍 Вы можете забрать посылку в пункте выдачи."
    )


def _split_long_text(text: str, max_len: int = 3600) -> list[str]:
    text = str(text or "")
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    cur = ""
    for line in text.split("\n"):
        candidate = (cur + "\n" + line) if cur else line
        if len(candidate) > max_len:
            if cur:
                parts.append(cur)
                cur = line
            else:
                parts.append(line[:max_len])
                cur = line[max_len:]
        else:
            cur = candidate
    if cur:
        parts.append(cur)
    return [p for p in parts if p.strip()]


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

    shipments = list(qs.only("id", "user_id", "tracking_number", "status", "weight_kg", "total_price").iterator(chunk_size=500))
    idx = 0
    for _ in shipments:
        idx += 1
        if idx % 200 == 0:
            self.update_state(state="PROGRESS", meta={"current": idx, "total": total, "sent": sent, "failed": failed})

    user_ids = sorted({int(s.user_id) for s in shipments if getattr(s, "user_id", None)})
    user_map = {
        int(u.id): (getattr(u, "telegram_id", None) or None)
        for u in tg_models.User.objects.filter(id__in=user_ids).only("id", "telegram_id")
    }

    grouped: dict[tuple[int, str], dict] = {}
    for sh in shipments:
        try:
            uid = int(sh.user_id)
        except Exception:
            continue
        status = str(getattr(sh, "status", "") or "")
        key = (uid, status)
        entry = grouped.get(key)
        if entry is None:
            entry = {"trackings": [], "items": []}
            grouped[key] = entry
        entry["trackings"].append(str(getattr(sh, "tracking_number", "") or ""))
        entry["items"].append(
            {
                "tracking": str(getattr(sh, "tracking_number", "") or ""),
                "weight_kg": getattr(sh, "weight_kg", None),
                "total_price": getattr(sh, "total_price", None),
            }
        )

    token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
    if not token:
        return {"current": total, "total": total, "sent": 0, "failed": total}

    for (uid, status), payload in grouped.items():
        chat_id = user_map.get(uid)
        if not chat_id:
            failed += 1
            continue

        text = ""
        if status == tg_models.Shipment.Status.WAREHOUSE:
            text = _shipment_notify_text_ready_for_pickup_batch(payload.get("items") or [])
        elif status == tg_models.Shipment.Status.ON_THE_WAY:
            text = _shipment_notify_text_in_transit_batch(payload.get("trackings") or [])
        else:
            text = _shipment_notify_text_bishkek_batch(payload.get("trackings") or [])

        chunks = _split_long_text(text)
        ok_all = True
        for chunk in chunks:
            ok = _send_telegram_message(token=token, chat_id=int(chat_id), text=chunk)
            if not ok:
                ok_all = False
                break

        if ok_all:
            sent += 1
        else:
            failed += 1

    self.update_state(state="SUCCESS", meta={"current": total, "total": total, "sent": sent, "failed": failed})
    return {"current": total, "total": total, "sent": sent, "failed": failed}


@shared_task(bind=True)
def notify_group_status_task(self, group_id: int, shipment_status: str, filial_id: Optional[int] = None) -> dict:
    try:
        gid = int(group_id)
    except Exception:
        gid = 0

    status = str(shipment_status or "")

    qs = tg_models.Shipment.objects.filter(group_id=gid, status=status).exclude(user__isnull=True)
    if filial_id is not None:
        try:
            fid = int(filial_id)
        except Exception:
            fid = 0
        if fid:
            qs = qs.filter(filial_id=fid)

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

    shipments = list(qs.only("id", "user_id", "tracking_number", "status", "weight_kg", "total_price").iterator(chunk_size=500))

    user_ids = sorted({int(s.user_id) for s in shipments if getattr(s, "user_id", None)})
    user_map = {
        int(u.id): (getattr(u, "telegram_id", None) or None)
        for u in tg_models.User.objects.filter(id__in=user_ids).only("id", "telegram_id")
    }

    grouped: dict[int, dict] = {}
    for sh in shipments:
        try:
            uid = int(sh.user_id)
        except Exception:
            continue
        entry = grouped.get(uid)
        if entry is None:
            entry = {"trackings": [], "items": []}
            grouped[uid] = entry
        entry["trackings"].append(str(getattr(sh, "tracking_number", "") or ""))
        entry["items"].append(
            {
                "tracking": str(getattr(sh, "tracking_number", "") or ""),
                "weight_kg": getattr(sh, "weight_kg", None),
                "total_price": getattr(sh, "total_price", None),
            }
        )

    token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
    if not token:
        return {"current": total, "total": total, "sent": 0, "failed": total}

    idx = 0
    for uid, payload in grouped.items():
        idx += 1
        if idx % 25 == 0:
            self.update_state(state="PROGRESS", meta={"current": idx, "total": len(grouped), "sent": sent, "failed": failed})

        chat_id = user_map.get(uid)
        if not chat_id:
            failed += 1
            continue

        if status == tg_models.Shipment.Status.WAREHOUSE:
            text = _shipment_notify_text_ready_for_pickup_batch(payload.get("items") or [])
        elif status == tg_models.Shipment.Status.ON_THE_WAY:
            text = _shipment_notify_text_in_transit_batch(payload.get("trackings") or [])
        else:
            text = _shipment_notify_text_bishkek_batch(payload.get("trackings") or [])

        chunks = _split_long_text(text)
        ok_all = True
        for chunk in chunks:
            ok = _send_telegram_message(token=token, chat_id=int(chat_id), text=chunk)
            if not ok:
                ok_all = False
                break

        if ok_all:
            sent += 1
        else:
            failed += 1

    self.update_state(state="SUCCESS", meta={"current": total, "total": total, "sent": sent, "failed": failed})
    return {"current": total, "total": total, "sent": sent, "failed": failed}
