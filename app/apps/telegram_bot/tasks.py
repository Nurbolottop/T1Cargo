import logging

from celery import shared_task

from decimal import Decimal
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
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
        "Ваш товар прибыл в Кыргызстан KG\n\n"
        "🧾 Трек-номера:\n"
        f"{list_block}\n\n"
        "🛠 Сейчас посылка проходит оформление\n"
        "и подготовку к выдаче.\n\n"
        "🔔 Скоро отправим сообщение о готовности."
    )


def _shipment_notify_text_ready_for_pickup_batch(items: list[dict]) -> str:
    lines = []
    total_price = Decimal("0")
    for it in items:
        t = (str(it.get("tracking") or "—")).strip() or "—"
        w = it.get("weight_kg")
        p = it.get("total_price")
        extra = []
        if w is not None and str(w).strip() != "":
            extra.append(f"{w} кг")
        if p is not None and str(p).strip() != "":
            extra.append(f"{p} сом")
            try:
                total_price += Decimal(str(p))
            except Exception:
                pass
        suffix = (" — " + ", ".join(extra)) if extra else ""
        lines.append(f"• {t}{suffix}")
    list_block = "\n".join(lines) if lines else "—"
    total_line = ""
    if total_price > 0:
        total_line = f"\n\n💰 Итого к оплате: {total_price} сом"
    return (
        "✅📦 Посылка готова к выдаче!\n\n"
        "🧾 Трек-номера:\n"
        f"{list_block}\n\n"
        "🆓 Бесплатное хранение — 3 дня\n"
        "⏳ Далее начисляется плата за хранение.\n\n"
        "📍 Вы можете забрать посылку в пункте выдачи."
        f"{total_line}"
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


def _send_text_to_chat(token: str, chat_id: int, text: str) -> bool:
    chunks = _split_long_text(text)
    for chunk in chunks:
        ok = _send_telegram_message(token=token, chat_id=int(chat_id), text=chunk)
        if not ok:
            return False
    return True


def _penalty_reminder_text(has_debt: bool, has_penalty: bool, has_accrual: bool) -> str:
    lines = ["⚠️ Напоминание"]
    if has_debt:
        lines.append("• У вас есть долг")
    if has_penalty:
        lines.append("• У вас есть штраф за хранение")
    if has_accrual:
        lines.append("• По посылкам начисляется плата за хранение")
    lines.append("")
    lines.append("Пожалуйста, оплатите задолженность/штраф и заберите посылки как можно скорее.")
    return "\n".join(lines)


@shared_task(bind=True)
def broadcast_to_clients_task(self, text: str, filial_id: Optional[int] = None) -> dict:
    try:
        settings_obj = base_models.Settings.objects.first()
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("broadcast_to_clients_task: database not ready: %s", exc)
        return {"sent": 0, "failed": 0, "total": 0}

    token = (getattr(settings_obj, "telegram_token", "") or "").strip()
    if not token:
        logger.error("broadcast_to_clients_task: telegram_token is empty")
        return {"sent": 0, "failed": 0, "total": 0}

    qs = tg_models.User.objects.exclude(telegram_id__isnull=True).exclude(telegram_id=0)
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

    logger.info(
        "broadcast_to_clients_task started (filial_id=%s, recipients=%s)",
        filial_id,
        total,
    )
    self.update_state(state="PROGRESS", meta={"current": 0, "total": total, "sent": 0, "failed": 0})

    sent = 0
    failed = 0
    idx = 0
    for u in qs.only("id", "telegram_id").iterator(chunk_size=500):
        idx += 1
        if idx % 100 == 0:
            self.update_state(state="PROGRESS", meta={"current": idx, "total": total, "sent": sent, "failed": failed})
        chat_id = getattr(u, "telegram_id", None)
        if not chat_id:
            failed += 1
            continue
        ok = _send_text_to_chat(token=token, chat_id=int(chat_id), text=str(text or ""))
        if ok:
            sent += 1
        else:
            failed += 1

    logger.info(
        "broadcast_to_clients_task finished (filial_id=%s, total=%s, sent=%s, failed=%s)",
        filial_id,
        total,
        sent,
        failed,
    )
    self.update_state(state="SUCCESS", meta={"current": total, "total": total, "sent": sent, "failed": failed})
    return {"total": total, "sent": sent, "failed": failed}


@shared_task(bind=True)
def remind_penalties_and_debts_task(self, filial_id: Optional[int] = None) -> dict:
    token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
    if not token:
        return {"sent": 0, "failed": 0, "total": 0}

    user_qs = tg_models.User.objects.exclude(telegram_id__isnull=True).exclude(telegram_id=0)
    if filial_id is not None:
        try:
            fid = int(filial_id)
        except Exception:
            fid = 0
        if fid:
            user_qs = user_qs.filter(filial_id=fid)

    today = timezone.localdate()
    free_days = 3
    cutoff = today - timezone.timedelta(days=free_days)

    accrual_user_ids = set(
        tg_models.Shipment.objects.select_related("user", "user__filial")
        .filter(status=tg_models.Shipment.Status.WAREHOUSE)
        .exclude(user__isnull=True)
        .exclude(arrival_date__isnull=True)
        .filter(arrival_date__lt=cutoff)
        .filter(user__filial__storage_penalty_per_day__gt=0)
        .values_list("user_id", flat=True)
        .distinct()
    )

    total = 0
    sent = 0
    failed = 0

    for u in user_qs.only("id", "telegram_id", "total_debt", "storage_penalty_total").iterator(chunk_size=500):
        uid = getattr(u, "id", None)
        chat_id = getattr(u, "telegram_id", None)
        if not uid or not chat_id:
            continue

        has_debt = False
        has_penalty = False
        try:
            has_debt = Decimal(str(getattr(u, "total_debt", 0) or 0)) > 0
        except Exception:
            has_debt = False
        try:
            has_penalty = Decimal(str(getattr(u, "storage_penalty_total", 0) or 0)) > 0
        except Exception:
            has_penalty = False
        has_accrual = int(uid) in accrual_user_ids

        if not (has_debt or has_penalty or has_accrual):
            continue

        total += 1
        text = _penalty_reminder_text(has_debt=has_debt, has_penalty=has_penalty, has_accrual=has_accrual)
        ok = _send_text_to_chat(token=token, chat_id=int(chat_id), text=text)
        if ok:
            sent += 1
        else:
            failed += 1

    return {"total": total, "sent": sent, "failed": failed}


@shared_task(bind=True)
def remind_ready_for_pickup_task(self, filial_id: Optional[int] = None) -> dict:
    token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
    if not token:
        return {"sent": 0, "failed": 0, "total": 0}

    qs = tg_models.Shipment.objects.filter(status=tg_models.Shipment.Status.WAREHOUSE).exclude(user__isnull=True)
    if filial_id is not None:
        try:
            fid = int(filial_id)
        except Exception:
            fid = 0
        if fid:
            qs = qs.filter(filial_id=fid)

    shipments = list(qs.only("id", "user_id", "group_id", "tracking_number", "weight_kg", "total_price").iterator(chunk_size=1000))
    if not shipments:
        return {"total": 0, "sent": 0, "failed": 0}

    user_ids = sorted({int(s.user_id) for s in shipments if getattr(s, "user_id", None)})
    user_map = {
        int(u.id): (getattr(u, "telegram_id", None) or None)
        for u in tg_models.User.objects.filter(id__in=user_ids).only("id", "telegram_id")
    }

    grouped: dict[tuple[int, int], list[dict]] = {}
    for sh in shipments:
        try:
            uid = int(sh.user_id)
        except Exception:
            continue
        gid = getattr(sh, "group_id", None)
        try:
            gid_int = int(gid) if gid is not None else 0
        except Exception:
            gid_int = 0
        key = (uid, gid_int)
        bucket = grouped.get(key)
        if bucket is None:
            bucket = []
            grouped[key] = bucket
        bucket.append(
            {
                "tracking": str(getattr(sh, "tracking_number", "") or ""),
                "weight_kg": getattr(sh, "weight_kg", None),
                "total_price": getattr(sh, "total_price", None),
            }
        )

    total = len(grouped)
    sent = 0
    failed = 0

    idx = 0
    for (uid, _gid_int), items in grouped.items():
        idx += 1
        if idx % 50 == 0:
            self.update_state(state="PROGRESS", meta={"current": idx, "total": total, "sent": sent, "failed": failed})

        chat_id = user_map.get(uid)
        if not chat_id:
            failed += 1
            continue

        text = _shipment_notify_text_ready_for_pickup_batch(items)
        ok = _send_text_to_chat(token=token, chat_id=int(chat_id), text=text)
        if ok:
            sent += 1
        else:
            failed += 1

    return {"total": total, "sent": sent, "failed": failed}


def _send_user_arrival_notification(user_id: int, tracking: str, shipment_status: str, weight_kg=None, total_price=None) -> bool:
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
        text = _shipment_notify_text_ready_for_pickup(tracking=tracking, weight_kg=weight_kg, total_price=total_price)
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
        "Ваш товар прибыл в Кыргызстан KG\n\n"
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


def _shipment_notify_text_ready_for_pickup_batch_total(shipments: list) -> str:
    """Send one message for all shipments with total weight and price"""
    if not shipments:
        return ""
    
    total_weight = Decimal("0")
    total_price = Decimal("0")
    tracking_numbers = []
    
    for shipment in shipments:
        tracking_numbers.append(shipment.tracking_number or "—")
        if shipment.weight_kg and shipment.weight_kg > 0:
            total_weight += shipment.weight_kg
        if shipment.total_price and shipment.total_price > 0:
            total_price += shipment.total_price
    
    # Format tracking list
    if len(tracking_numbers) <= 3:
        tracking_list = "\n".join([f"• {t}" for t in tracking_numbers])
    else:
        tracking_list = "\n".join([f"• {t}" for t in tracking_numbers[:3]])
        tracking_list += f"\n• ... и еще {len(tracking_numbers) - 3} посылок"
    
    weight_text = f"⚖️ Общий вес: {total_weight} кг\n" if total_weight > 0 else ""
    price_text = f"💰 Общая стоимость: {total_price} сом\n" if total_price > 0 else ""
    
    return (
        "✅📦 Ваши посылки готовы к выдаче!\n\n"
        f"🧾 Трек-номера ({len(tracking_numbers)} шт.):\n{tracking_list}\n\n"
        f"{weight_text}"
        f"{price_text}"
        "🆓 Бесплатное хранение — 3 дня\n"
        "⏳ Далее начисляется плата за хранение.\n\n"
        "📍 Вы можете забрать посылки в пункте выдачи."
    )


@shared_task
def notify_user_arrival_batch_task(user_id: int, shipments_data: list) -> bool:
    """Send one notification for multiple shipments"""
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

        # Get actual shipment objects
        shipment_ids = [s.get('id') for s in shipments_data]
        shipments = tg_models.Shipment.objects.filter(id__in=shipment_ids)
        
        text = _shipment_notify_text_ready_for_pickup_batch_total(shipments)
        
        ok = _send_telegram_message(token=token, chat_id=int(chat_id), text=text)
        if not ok:
            logger.exception(
                "telegram send failed (user_id=%s, shipments=%s)",
                user_id,
                shipment_ids,
            )
            return False
        return True
    except Exception as e:
        logger.exception(
            "notify_user_arrival_batch_task failed (user_id=%s): %s",
            user_id,
            e,
        )
        return False


@shared_task
def notify_user_arrival_task(user_id: int, tracking: str, shipment_status: str, weight_kg=None, total_price=None) -> bool:
    try:
        return _send_user_arrival_notification(user_id=user_id, tracking=tracking, shipment_status=shipment_status, weight_kg=weight_kg, total_price=total_price)
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
def notify_user_group_status_task(
    self,
    user_id: int,
    group_id: int,
    shipment_status: str,
    filial_id: Optional[int] = None,
) -> dict:
    try:
        uid = int(user_id)
    except Exception:
        uid = 0
    try:
        gid = int(group_id)
    except Exception:
        gid = 0

    status = str(shipment_status or "")

    qs = tg_models.Shipment.objects.filter(group_id=gid, user_id=uid, status=status)
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

    if total <= 0:
        return {"total": 0, "sent": 0, "failed": 0}

    if status == tg_models.Shipment.Status.WAREHOUSE:
        remaining_qs = tg_models.Shipment.objects.filter(group_id=gid, user_id=uid)
        if filial_id is not None:
            try:
                fid = int(filial_id)
            except Exception:
                fid = 0
            if fid:
                remaining_qs = remaining_qs.filter(filial_id=fid)
        remaining = remaining_qs.exclude(
            status__in=[tg_models.Shipment.Status.WAREHOUSE, tg_models.Shipment.Status.ISSUED]
        ).exists()
        if remaining:
            return {"total": total, "sent": 0, "failed": 0}

    token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
    if not token:
        return {"total": total, "sent": 0, "failed": total or 1}

    user_obj = tg_models.User.objects.filter(id=uid).only("id", "telegram_id").first()
    chat_id = getattr(user_obj, "telegram_id", None) if user_obj else None
    if not chat_id:
        return {"total": total, "sent": 0, "failed": total or 1}

    shipments = list(qs.only("tracking_number", "weight_kg", "total_price").iterator(chunk_size=500))
    items = [
        {
            "tracking": str(getattr(sh, "tracking_number", "") or ""),
            "weight_kg": getattr(sh, "weight_kg", None),
            "total_price": getattr(sh, "total_price", None),
        }
        for sh in shipments
    ]
    trackings = [str(getattr(sh, "tracking_number", "") or "") for sh in shipments]

    if status == tg_models.Shipment.Status.WAREHOUSE:
        text = _shipment_notify_text_ready_for_pickup_batch(items)
    elif status == tg_models.Shipment.Status.ON_THE_WAY:
        text = _shipment_notify_text_in_transit_batch(trackings)
    else:
        text = _shipment_notify_text_bishkek_batch(trackings)

    chunks = _split_long_text(text)
    for chunk in chunks:
        ok = _send_telegram_message(token=token, chat_id=int(chat_id), text=chunk)
        if not ok:
            return {"total": total, "sent": 0, "failed": 1}
    return {"total": total, "sent": 1, "failed": 0}


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
