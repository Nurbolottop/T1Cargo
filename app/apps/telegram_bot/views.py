from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

import json
import re
import secrets
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
    pvz_phone = (getattr(s, "phone", "") or "").strip() if s else ""
    pvz_wh = (
        base_models.Warehouse.objects.filter(country__icontains="кыргыз").order_by("city", "name").first()
        or base_models.Warehouse.objects.filter(country__icontains="kyrgyz").order_by("city", "name").first()
        or base_models.Warehouse.objects.order_by("country", "city", "name").first()
    )

    data = {
        "client_code": user_obj.client_code or "",
        "full_name": user_obj.full_name or "",
        "phone": user_obj.phone or "",
        "address": user_obj.address or "",
        "pvz_city": getattr(pvz_wh, "city", "") or "",
        "pvz_phone": pvz_phone,
        "manager_contact": (getattr(s, "manager_contact", "") or "").strip() if s else "",
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
    pvz_phone = (getattr(s, "phone", "") or "").strip() if s else ""
    pvz_city = ""
    pvz_wh = (
        base_models.Warehouse.objects.filter(country__icontains="кыргыз").order_by("city", "name").first()
        or base_models.Warehouse.objects.filter(country__icontains="kyrgyz").order_by("city", "name").first()
        or base_models.Warehouse.objects.order_by("country", "city", "name").first()
    )
    if pvz_wh:
        pvz_city = getattr(pvz_wh, "city", "") or ""

    china_wh = (
        base_models.Warehouse.objects.filter(country__icontains="китай").order_by("city", "name").first()
        or base_models.Warehouse.objects.filter(country__icontains="china").order_by("city", "name").first()
    )
    china_address = (getattr(china_wh, "address", "") or "").strip() if china_wh else ""
    code_value = (user_obj.client_code or "—").strip()
    tg_id_value = str(telegram_user_id)
    copy_lines = "\n".join([code_value, tg_id_value, china_address or "—", code_value])

    data = {
        "copy_lines": copy_lines,
        "pvz_city": pvz_city,
        "pvz_phone": pvz_phone,
    }
    return JsonResponse({"ok": True, "data": data})


@csrf_exempt
def webapp_profile_instructions(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    _, user_obj = _get_user_by_payload(payload)
    if not user_obj:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    qs = base_models.Instruction.objects.all().order_by("-created_at")
    items = []
    for instr in qs[:50]:
        items.append({"id": instr.id, "title": (instr.title or "").strip()})
    return JsonResponse({"ok": True, "data": {"items": items}})


@csrf_exempt
def webapp_profile_instruction_detail(request, instruction_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    _, user_obj = _get_user_by_payload(payload)
    if not user_obj:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    instr = base_models.Instruction.objects.filter(id=instruction_id).first()
    if not instr:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    photo_url = ""
    try:
        photo = getattr(instr, "photo", None)
        if photo and getattr(photo, "url", None):
            photo_url = photo.url
    except Exception:
        photo_url = ""

    file_url = ""
    try:
        f = getattr(instr, "file", None)
        if f and getattr(f, "url", None):
            file_url = f.url
    except Exception:
        file_url = ""

    data = {
        "title": (instr.title or "").strip(),
        "text": _html_to_text(str(instr.text or "")),
        "video_url": (getattr(instr, "video_url", "") or "").strip(),
        "link_url": (getattr(instr, "link_url", "") or "").strip(),
        "photo_url": photo_url,
        "file_url": file_url,
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
    manager_contact = (getattr(s, "manager_contact", "") or "").strip() if s else ""
    instagram_url = (getattr(s, "instagram_url", "") or "").strip() if s else ""
    pvz_location_url = (getattr(s, "pvz_location_url", "") or "").strip() if s else ""
    work_hours = (getattr(s, "work_hours", "") or "").strip() if s else ""
    pvz_phone = (getattr(s, "phone", "") or "").strip() if s else ""

    pvz_wh = (
        base_models.Warehouse.objects.filter(country__icontains="кыргыз").order_by("city", "name").first()
        or base_models.Warehouse.objects.filter(country__icontains="kyrgyz").order_by("city", "name").first()
        or base_models.Warehouse.objects.order_by("country", "city", "name").first()
    )
    pvz_city = (getattr(pvz_wh, "city", "") or "").strip() if pvz_wh else ""

    data = {
        "manager_contact": manager_contact,
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
) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    if disable_web_page_preview:
        payload["disable_web_page_preview"] = "true"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10):
        return


def _generate_client_code(prefix: str = "T1") -> str:
    prefix = (prefix or "T1").strip().upper()
    if not prefix:
        prefix = "T1"

    for _ in range(50):
        number = secrets.randbelow(9000) + 1000
        candidate = f"{prefix}-{number}"
        if not tg_models.User.objects.filter(client_code=candidate).exists():
            return candidate
    return f"{prefix}-{secrets.randbelow(900000) + 100000}"

@csrf_exempt
def webapp_register_submit(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    full_name = (payload.get("full_name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    address = (payload.get("address") or "").strip()

    telegram_user_id = payload.get("telegram_user_id")
    telegram_username = (payload.get("telegram_username") or "").strip()

    if not full_name or not phone:
        return JsonResponse({"ok": False, "error": "validation"}, status=400)

    user_obj = None
    if isinstance(telegram_user_id, int):
        user_obj, _ = tg_models.User.objects.update_or_create(
            telegram_id=telegram_user_id,
            defaults={
                "username": telegram_username,
                "full_name": full_name,
                "phone": phone,
                "address": address,
                "status": tg_models.User.Status.CLIENT_REGISTERED,
            },
        )

        if user_obj and not user_obj.client_code:
            user_obj.client_code = _generate_client_code("T1")
            user_obj.save(update_fields=["client_code", "updated_at"])

    settings_obj = base_models.Settings.objects.first()
    if settings_obj and settings_obj.is_bot_enabled and settings_obj.telegram_token:
        if user_obj and isinstance(telegram_user_id, int):
            menu_kb = {
                "keyboard": [
                    ["👤 Профиль", "🎁 Адреса", "📦 Мои посылки"],
                    ["📕 Инструкция", "⛔ Запрещенные товары", "⚙ Поддержка"],
                    ["✅ Добавить трек"],
                ],
                "resize_keyboard": True,
            }

            manager_url = ""
            manager_contact = (settings_obj.manager_contact or "").strip()
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

            inline_kb = {"inline_keyboard": []}
            if manager_url:
                inline_kb["inline_keyboard"].append([
                    {"text": "WhatsApp менеджера", "url": manager_url}
                ])
            if (settings_obj.website or "").strip().startswith("http"):
                inline_kb["inline_keyboard"].append([
                    {"text": "Войти в личный кабинет", "url": settings_obj.website}
                ])

            code = user_obj.client_code or ""
            profile_text = (
                "🎉 Регистрация прошла успешно 🎉\n"
                "Спасибо что подписались\n\n"
                "📄 Ваш профиль 📄\n\n"
                f"🪪 Персональный КОД: {code}\n"
                f"👤 ФИО: {full_name or ''}\n"
                f"📞 Номер: {phone or ''}\n"
                f"🏡 Адрес: {address or ''}"
            )
            try:
                if inline_kb["inline_keyboard"]:
                    _send_telegram_message(settings_obj.telegram_token, telegram_user_id, profile_text, reply_markup=inline_kb)
                    _send_telegram_message(settings_obj.telegram_token, telegram_user_id, "Меню:", reply_markup=menu_kb)
                else:
                    _send_telegram_message(settings_obj.telegram_token, telegram_user_id, profile_text, reply_markup=menu_kb)
            except Exception:
                pass

            china_wh = (
                base_models.Warehouse.objects.filter(country__icontains="китай").order_by("city", "name").first()
                or base_models.Warehouse.objects.filter(country__icontains="china").order_by("city", "name").first()
            )
            china_address = getattr(china_wh, "address", "").strip() if china_wh else ""
            manager_phone = (settings_obj.phone or "").strip()

            address_text = (
                "📩 Скопируйте ниже. Это адрес склада в Китае 🇨🇳\n\n"
                f"{user_obj.client_code or '—'}\n"
                f"{telegram_user_id}\n"
                f"{china_address or '—'}\n"
                f"{user_obj.client_code or '—'}\n\n"
                "Чтобы ваши посылки не потерялись обязательно отправьте скрин заполненного адреса "
                "и получите подтверждение от нашего менеджера\n\n"
                f"📱 {manager_phone or '—'}\n\n"
                "❗❗❗ Только после подтверждения ✅ адреса Карго несет ответственность за ваши посылки 📦"
            )
            try:
                _send_telegram_message(settings_obj.telegram_token, telegram_user_id, address_text)
            except Exception:
                pass

    return JsonResponse({"ok": True})
