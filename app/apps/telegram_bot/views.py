from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

import json
import re
import urllib.parse
import urllib.request

from apps.base import models as base_models
from apps.telegram_bot import models as tg_models

# Create your views here.


def webapp_register(request):
    settings_obj = base_models.Settings.objects.first()
    return render(
        request,
        "telegram_bot/webapp_register.html",
        {"settings": settings_obj},
    )


def webapp_profile(request):
    settings_obj = base_models.Settings.objects.first()
    return render(
        request,
        "telegram_bot/webapp_profile.html",
        {"settings": settings_obj},
    )


def webapp_register_filials(request):
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    items = list(
        base_models.Filial.objects.filter(is_active=True)
        .order_by("city", "name")
        .values("id", "name", "city")
    )
    return JsonResponse({"ok": True, "data": items})


def webapp_register_preclient(request):
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    code = (request.GET.get("code") or "").strip()
    if not code:
        return JsonResponse({"ok": False, "error": "validation"}, status=400)

    qs = tg_models.User.objects.select_related("filial").filter(telegram_id__isnull=True)
    pre = qs.filter(client_code__iexact=code).first()
    if not pre and "-" not in code:
        pre = qs.filter(client_code__iendswith=f"-{code}").first()
    if not pre:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    return JsonResponse(
        {
            "ok": True,
            "data": {
                "client_code": pre.client_code,
                "phone": pre.phone,
                "filial_id": pre.filial_id,
            },
        }
    )


def _html_to_text(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""

    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*p\s*>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*p\b[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\r\n", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _normalize_phone(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return ""

    # Kyrgyzstan
    if digits.startswith("996"):
        return "+" + digits
    if len(digits) == 9:
        return "+996" + digits
    if len(digits) == 10 and digits.startswith("0"):
        return "+996" + digits[1:]

    # Russia
    if len(digits) == 11 and digits.startswith("8"):
        return "+7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    if len(digits) == 10:
        return "+7" + digits

    if s.startswith("+"):
        return "+" + digits
    return "+" + digits


def _normalize_client_code(raw: str, filial_obj: base_models.Filial | None) -> str:
    code = (raw or "").strip()
    if not code:
        return ""
    if "-" in code:
        return code.upper()

    prefix = (getattr(filial_obj, "client_code_prefix", "") or "").strip().upper() if filial_obj else ""
    if not prefix:
        return code
    return f"{prefix}-{code}"


def _get_user_by_payload(payload):
    telegram_user_id = payload.get("telegram_user_id") if isinstance(payload, dict) else None
    if not isinstance(telegram_user_id, int):
        return None, None
    user_obj = tg_models.User.objects.filter(telegram_id=telegram_user_id).first()
    return telegram_user_id, user_obj


@csrf_exempt
def webapp_profile_data(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    _, user_obj = _get_user_by_payload(payload)
    if not user_obj:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    s = base_models.Settings.objects.first()
    wh = base_models.Warehouse.objects.order_by("name").first()
    pvz_phone = (getattr(wh, "phone", "") or "").strip() if wh else (getattr(s, "phone", "") or "").strip() if s else ""

    filial_obj = getattr(user_obj, "filial", None)
    manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
    manager_url = ""
    if manager_contact:
        if manager_contact.startswith("http://") or manager_contact.startswith("https://"):
            manager_url = manager_contact
        elif manager_contact.startswith("@"):  # telegram
            u = manager_contact[1:]
            if u:
                manager_url = f"https://t.me/{u}"
        else:
            normalized = "".join(ch for ch in manager_contact if ch.isdigit())
            if normalized:
                manager_url = f"https://wa.me/{normalized}"

    data = {
        "client_code": user_obj.client_code or "",
        "full_name": user_obj.full_name or "",
        "phone": user_obj.phone or "",
        "address": user_obj.address or "",
        "pvz_city": "",
        "pvz_phone": pvz_phone,
        "manager_contact": manager_contact,
        "website": (getattr(s, "website", "") or "").strip() if s else "",
        "title": (getattr(s, "title", "") or "").strip() if s else "",
    }
    return JsonResponse({"ok": True, "data": data})


@csrf_exempt
def webapp_profile_parcels(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    _, user_obj = _get_user_by_payload(payload)
    if not user_obj:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    qs = tg_models.Shipment.objects.filter(user=user_obj).order_by("-created_at")
    items = []
    for sh in qs[:30]:
        items.append(
            {
                "tracking_number": sh.tracking_number,
                "status": sh.get_status_display(),
                "weight_kg": str(getattr(sh, "weight_kg", "") or ""),
                "total_price": str(getattr(sh, "total_price", "") or ""),
            }
        )

    return JsonResponse({"ok": True, "data": {"items": items}})


@csrf_exempt
def webapp_profile_addresses(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    telegram_user_id, user_obj = _get_user_by_payload(payload)
    if not user_obj:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    s = base_models.Settings.objects.first()
    wh = base_models.Warehouse.objects.order_by("name").first()
    warehouse_phone = (getattr(wh, "phone", "") or "").strip() if wh else (getattr(s, "phone", "") or "").strip() if s else ""
    pvz_phone = warehouse_phone
    pvz_city = ""
    china_address = (getattr(wh, "address", "") or "").strip() if wh else ""
    code_value = (user_obj.client_code or "—").strip()

    client_phone_digits = "".join(ch for ch in (user_obj.phone or "") if ch.isdigit())
    client_phone_suffix = f" ({client_phone_digits})" if client_phone_digits else ""
    copy_lines = "\n".join([
        f"阿{code_value}",
        warehouse_phone or "—",
        f"{(china_address or '—')}{code_value}{client_phone_suffix}",
    ])

    data = {
        "copy_lines": copy_lines,
        "pvz_city": pvz_city,
        "pvz_phone": pvz_phone,
    }
    return JsonResponse({"ok": True, "data": data})


@csrf_exempt
def webapp_profile_support(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    _, user_obj = _get_user_by_payload(payload)
    if not user_obj:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    s = base_models.Settings.objects.first()
    filial_obj = getattr(user_obj, "filial", None)
    manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
    manager_url = ""
    if manager_contact:
        if manager_contact.startswith("http://") or manager_contact.startswith("https://"):
            manager_url = manager_contact
        elif manager_contact.startswith("@"):  # telegram
            u = manager_contact[1:]
            if u:
                manager_url = f"https://t.me/{u}"
        else:
            normalized = "".join(ch for ch in manager_contact if ch.isdigit())
            if normalized:
                manager_url = f"https://wa.me/{normalized}"
    instagram_url = (getattr(filial_obj, "instagram_url", "") or "").strip() if filial_obj else ""
    pvz_location_url = (getattr(filial_obj, "pvz_location_url", "") or "").strip() if filial_obj else ""
    raw_hours = (getattr(filial_obj, "work_hours", "") or "") if filial_obj else ""
    work_hours = _html_to_text(str(raw_hours))
    wh = base_models.Warehouse.objects.order_by("name").first()
    pvz_phone = (getattr(wh, "phone", "") or "").strip() if wh else (getattr(s, "phone", "") or "").strip() if s else ""

    pvz_city = ""

    data = {
        "manager_contact": manager_contact,
        "manager_url": manager_url,
        "instagram_url": instagram_url,
        "pvz_location_url": pvz_location_url,
        "work_hours": work_hours,
        "pvz_city": pvz_city,
        "pvz_phone": pvz_phone,
    }
    return JsonResponse({"ok": True, "data": data})

def _send_telegram_message(
    token: str,
    chat_id: int,
    text: str,
    reply_markup: dict | None = None,
    disable_web_page_preview: bool = True,
    parse_mode: str | None = None,
) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_web_page_preview:
        payload["disable_web_page_preview"] = "true"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10):
        return


def _generate_client_code(filial_id: int | None) -> tuple[str, base_models.Filial | None]:
    with transaction.atomic():
        filial_obj = None
        if isinstance(filial_id, int):
            filial_obj = base_models.Filial.objects.select_for_update().filter(id=filial_id, is_active=True).first()

        if filial_obj is None:
            filial_obj = base_models.Filial.objects.select_for_update().filter(is_active=True).order_by("city", "name").first()

        if filial_obj is None:
            return "", None

        prefix = (getattr(filial_obj, "client_code_prefix", "T1") or "T1").strip().upper()
        start_number = int(getattr(filial_obj, "client_code_start_number", 1000) or 1000)
        last_number = getattr(filial_obj, "client_code_last_number", None)

        if not prefix:
            prefix = "T1"
        if start_number < 1:
            start_number = 1

        next_number = start_number if last_number is None else max(int(last_number) + 1, start_number)

        filial_obj.client_code_last_number = next_number
        filial_obj.save(update_fields=["client_code_last_number", "updated_at"])

    return f"{prefix}-{next_number}", filial_obj

@csrf_exempt
def webapp_register_submit(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    full_name = (payload.get("full_name") or "").strip()
    phone = _normalize_phone(payload.get("phone") or "")
    address = (payload.get("address") or "").strip()
    filial_id = payload.get("filial_id")
    existing_client_code = (payload.get("client_code") or "").strip()

    telegram_user_id = payload.get("telegram_user_id")
    telegram_username = (payload.get("telegram_username") or "").strip()

    if not full_name or not phone:
        return JsonResponse({"ok": False, "error": "validation"}, status=400)

    user_obj = None
    if isinstance(telegram_user_id, int):
        user_obj = tg_models.User.objects.filter(telegram_id=telegram_user_id).first()

        selected_filial_id = filial_id if isinstance(filial_id, int) else None
        filial_obj = base_models.Filial.objects.filter(id=selected_filial_id, is_active=True).first() if selected_filial_id else None
        if filial_obj is None:
            filial_obj = base_models.Filial.objects.filter(is_active=True).order_by("city", "name").first()
        if filial_obj is None:
            return JsonResponse({"ok": False, "error": "no_filials"}, status=400)

        normalized_client_code = _normalize_client_code(existing_client_code, filial_obj)

        reserved_user_obj = None
        if normalized_client_code:
            reserved_user_obj = (
                tg_models.User.objects.select_related("filial")
                .filter(client_code__iexact=normalized_client_code, telegram_id__isnull=True)
                .first()
            )

            # Code is considered "taken" if another registered user already has it.
            # If there is a reserved record (telegram_id is null), we will attach to it.
            if user_obj:
                if tg_models.User.objects.filter(client_code__iexact=normalized_client_code).exclude(id=user_obj.id).exists():
                    return JsonResponse({"ok": False, "error": "code_taken"}, status=400)
            else:
                taken_registered = tg_models.User.objects.filter(
                    client_code__iexact=normalized_client_code,
                    telegram_id__isnull=False,
                ).exists()
                if taken_registered:
                    return JsonResponse({"ok": False, "error": "code_taken"}, status=400)

        if user_obj:
            user_obj.username = telegram_username
            user_obj.full_name = full_name
            user_obj.phone = phone
            user_obj.address = address
            user_obj.status = tg_models.User.Status.CLIENT_REGISTERED
            user_obj.filial = filial_obj
            if not user_obj.client_type:
                user_obj.client_type = tg_models.User.ClientType.INDIVIDUAL

            if normalized_client_code:
                user_obj.client_code = normalized_client_code
                user_obj.client_status = tg_models.User.ClientStatus.OLD
            else:
                user_obj.client_status = tg_models.User.ClientStatus.NEW
                if not user_obj.client_code:
                    code, locked_filial_obj = _generate_client_code(filial_obj.id)
                    if not code:
                        return JsonResponse({"ok": False, "error": "no_filials"}, status=400)
                    user_obj.client_code = code
                    if locked_filial_obj:
                        user_obj.filial = locked_filial_obj
            user_obj.save()
        else:
            if normalized_client_code and reserved_user_obj:
                user_obj = reserved_user_obj
                user_obj.telegram_id = telegram_user_id
                user_obj.username = telegram_username
                user_obj.full_name = full_name
                user_obj.phone = phone
                user_obj.address = address
                user_obj.status = tg_models.User.Status.CLIENT_REGISTERED
                if not user_obj.client_type:
                    user_obj.client_type = tg_models.User.ClientType.INDIVIDUAL
                if filial_obj:
                    user_obj.filial = filial_obj
                user_obj.client_status = tg_models.User.ClientStatus.OLD
                user_obj.save()
            elif normalized_client_code:
                user_obj = tg_models.User.objects.create(
                    telegram_id=telegram_user_id,
                    username=telegram_username,
                    full_name=full_name,
                    phone=phone,
                    address=address,
                    status=tg_models.User.Status.CLIENT_REGISTERED,
                    filial=filial_obj,
                    client_code=normalized_client_code,
                    client_type=tg_models.User.ClientType.INDIVIDUAL,
                    client_status=tg_models.User.ClientStatus.OLD,
                )
            else:
                locked_filial_obj = None
                code, locked_filial_obj = _generate_client_code(filial_obj.id)
                if not code:
                    return JsonResponse({"ok": False, "error": "no_filials"}, status=400)

                user_obj = tg_models.User.objects.create(
                    telegram_id=telegram_user_id,
                    username=telegram_username,
                    full_name=full_name,
                    phone=phone,
                    address=address,
                    status=tg_models.User.Status.CLIENT_REGISTERED,
                    filial=locked_filial_obj or filial_obj,
                    client_code=code,
                    client_type=tg_models.User.ClientType.INDIVIDUAL,
                    client_status=tg_models.User.ClientStatus.NEW,
                )

    settings_obj = base_models.Settings.objects.first()
    if settings_obj and settings_obj.is_bot_enabled and settings_obj.telegram_token:
        if user_obj and isinstance(telegram_user_id, int):
            menu_kb = {
                "keyboard": [
                    ["👤 Профиль", "🎁 Адреса", "📦 Мои посылки"],
                    ["🛒 Оптовый заказ", "⛔ Запрещенные товары", "⚙ Поддержка"],
                    ["✅ Добавить трек"],
                ],
                "resize_keyboard": True,
            }

            manager_url = ""
            filial_obj = getattr(user_obj, "filial", None)
            manager_contact = (getattr(filial_obj, "manager_contact", "") or "").strip() if filial_obj else ""
            if not manager_contact:
                manager_contact = (settings_obj.phone or "").strip()
            if manager_contact:
                if manager_contact.startswith("http://") or manager_contact.startswith("https://"):
                    manager_url = manager_contact
                elif manager_contact.startswith("@"):  # telegram
                    u = manager_contact[1:]
                    if u:
                        manager_url = f"https://t.me/{u}"
                else:
                    normalized = "".join(ch for ch in manager_contact if ch.isdigit())
                    if normalized:
                        manager_url = f"https://wa.me/{normalized}"

            try:
                _send_telegram_message(
                    settings_obj.telegram_token,
                    telegram_user_id,
                    "🎉 Регистрация прошла успешно 🎉\nСпасибо что подписались",
                )
            except Exception:
                pass

            wh = base_models.Warehouse.objects.order_by("name").first()
            china_address = (getattr(wh, "address", "") or "").strip() if wh else ""
            warehouse_phone = (getattr(wh, "phone", "") or "").strip() if wh else (settings_obj.phone or "").strip()
            code_value = (user_obj.client_code or "—").strip()

            client_phone_digits = "".join(ch for ch in (phone or "") if ch.isdigit())
            client_phone_suffix = f" ({client_phone_digits})" if client_phone_digits else ""

            address_text = "\n".join([
                f"阿{code_value}",
                warehouse_phone or "—",
                f"{(china_address or '—')}{code_value}{client_phone_suffix}",
            ])
            try:
                _send_telegram_message(
                    settings_obj.telegram_token,
                    telegram_user_id,
                    f"`{address_text}`",
                    reply_markup=menu_kb,
                    parse_mode="Markdown",
                )
            except Exception:
                pass

            warning_text = (
                "✅ *Важно*\n\n"
                "Чтобы ваши посылки не потерялись, обязательно отправьте менеджеру *скрин* "
                "заполненного адреса и получите *подтверждение* ✅\n\n"
                f"📱 *Телефон*: {(settings_obj.phone or '').strip() or '—'}\n\n"
                "❗❗❗ Только после подтверждения ✅ адреса Карго несет ответственность за ваши посылки 📦"
            )
            warn_kb = {"inline_keyboard": []}
            if manager_url:
                warn_kb["inline_keyboard"].append([
                    {"text": "WhatsApp менеджера", "url": manager_url}
                ])
            try:
                _send_telegram_message(
                    settings_obj.telegram_token,
                    telegram_user_id,
                    warning_text,
                    reply_markup=warn_kb if warn_kb["inline_keyboard"] else None,
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    return JsonResponse({"ok": True})
