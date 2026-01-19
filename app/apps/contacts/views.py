from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from decimal import Decimal, InvalidOperation
import os
import tempfile
import uuid
from django.db import transaction
from django.db.models import Count, Q, F, Sum, ExpressionWrapper, DecimalField, Value
from django.db import models
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from django.db.models.functions import Coalesce, TruncDate

from apps.telegram_bot import models as tg_models
from apps.base import models as base_models
from apps.telegram_bot.views import _send_telegram_message
from .forms import ClientEditDirectorForm, ClientEditManagerForm, ShipmentCreateForm, ShipmentImportForm


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


def _shipment_notify_text_issued(tracking: str) -> str:
    tracking = (tracking or "—").strip() or "—"
    return (
        "🎉📦 Ваш товар выдан!\n\n"
        f"🧾 Трек-номер: {tracking}\n\n"
        "🙏 Спасибо, что выбрали нашу карго-компанию.\n"
        "Будем рады вашим следующим отправкам!"
    )

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover
    load_workbook = None


def _get_staff_role(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    if getattr(user, "is_superuser", False):
        return "superuser"
    try:
        staff = user.userssh
    except Exception:
        staff = None
    return str(getattr(staff, "role", "") or "")


def _is_director(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return _get_staff_role(user) == tg_models.UsersSH.Role.DIRECTOR


def _is_manager(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return _get_staff_role(user) == tg_models.UsersSH.Role.MANAGER


def _role_ctx(request) -> dict:
    u = getattr(request, "user", None)
    is_director = _is_director(u)
    is_manager = _is_manager(u)

    filial_display = ""
    try:
        staff = u.userssh if u and getattr(u, "is_authenticated", False) else None
    except Exception:
        staff = None
    filial_obj = getattr(staff, "filial", None) if staff else None
    role = str(getattr(staff, "role", "") or "") if staff else ""
    if filial_obj is not None:
        filial_display = str(filial_obj)
    elif role == tg_models.UsersSH.Role.DIRECTOR or getattr(u, "is_superuser", False):
        filial_display = "Все филиалы"

    return {"is_director": is_director, "is_manager": is_manager, "filial_display": filial_display}


def _get_staff_filial_or_denied(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, redirect("manager_login")

    if getattr(user, "is_superuser", False):
        return None, None

    try:
        staff = user.userssh
    except Exception:
        staff = None

    filial = getattr(staff, "filial", None) if staff else None
    role = str(getattr(staff, "role", "") or "") if staff else ""
    if filial is None:
        if role == tg_models.UsersSH.Role.DIRECTOR:
            return None, None
        return None, HttpResponseForbidden("Не задан филиал для сотрудника")
    return filial, None


def _manager_access_check(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not bool(getattr(user, "is_staff", False)):
        return False
    role = _get_staff_role(user)
    if not role:
        return False
    return role in {tg_models.UsersSH.Role.MANAGER, tg_models.UsersSH.Role.DIRECTOR}


@never_cache
@csrf_protect
def manager_login(request):
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if _manager_access_check(request):
                if _is_director(user):
                    return redirect("manager_dashboard")
                return redirect("manager_shipments")

            reason = "Нет доступа"
            if not bool(getattr(user, "is_staff", False)) and not bool(getattr(user, "is_superuser", False)):
                reason = "Нет доступа: включите is_staff у пользователя"
            else:
                try:
                    prof = user.userssh
                except Exception:
                    prof = None
                if not prof:
                    reason = "Нет доступа: создайте запись UsersSH (Штатные) для пользователя и выберите роль"
                else:
                    role = str(getattr(prof, "role", "") or "")
                    if role not in {tg_models.UsersSH.Role.MANAGER, tg_models.UsersSH.Role.DIRECTOR}:
                        reason = "Нет доступа: роль должна быть Менеджер или Директор"

            logout(request)
            return render(
                request,
                "contacts/manager/login.html",
                {"error": reason},
            )
        return render(
            request,
            "contacts/manager/login.html",
            {"error": "Неверный логин или пароль"},
        )

    if request.user.is_authenticated and _manager_access_check(request):
        if _is_director(request.user):
            return redirect("manager_dashboard")
        return redirect("manager_shipments")

    return render(request, "contacts/manager/login.html")


def manager_logout(request):
    logout(request)
    return redirect("manager_login")


def _require_manager(request):
    if not _manager_access_check(request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return redirect("manager_login")
        return HttpResponseForbidden("Нет доступа")
    return None


def _require_director(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied
    if not _is_director(getattr(request, "user", None)):
        return HttpResponseForbidden("Нет доступа")
    return None


def _require_manager_role(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied
    if not _is_manager(getattr(request, "user", None)):
        return HttpResponseForbidden("Нет доступа")
    return None


def _require_editor_role(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied
    user = getattr(request, "user", None)
    if not (_is_manager(user) or _is_director(user)):
        return HttpResponseForbidden("Нет доступа")
    return None


@login_required(login_url="/manager/login/")
def manager_dashboard(request):
    denied = _require_director(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    selected_filial = None
    filial_raw = (request.GET.get("filial") or "").strip()
    if filial_raw:
        try:
            filial_id = int(filial_raw)
        except Exception:
            filial_id = None
        if filial_id:
            selected_filial = base_models.Filial.objects.filter(id=filial_id).first()

    effective_filial = selected_filial

    shipments_qs = tg_models.Shipment.objects.all()
    users_qs = tg_models.User.objects.all()
    groups_qs = tg_models.ShipmentGroup.objects.all()
    if effective_filial is not None:
        shipments_qs = shipments_qs.filter(filial=effective_filial)
        users_qs = users_qs.filter(filial=effective_filial)
        groups_qs = groups_qs.filter(filial=effective_filial)

    counts = (
        shipments_qs.values("status")
        .annotate(c=Count("id"))
        .order_by("status")
    )
    status_map = {row["status"]: row["c"] for row in counts}
    total_shipments = sum(status_map.values())

    since = timezone.now() - timezone.timedelta(days=7)
    new_clients_7d = users_qs.filter(created_at__gte=since).count()

    shipments_7d = shipments_qs.filter(created_at__gte=since).count()
    today = timezone.localdate()
    shipments_today = shipments_qs.filter(created_at__date=today).count()

    total_groups = groups_qs.count()
    active_groups = groups_qs.exclude(status=tg_models.ShipmentGroup.Status.ISSUED).count()

    last_shipments = shipments_qs.select_related("user").order_by("-created_at")[:10]
    return render(
        request,
        "contacts/manager/dashboard.html",
        {
            "nav": "dashboard",
            "total_shipments": total_shipments,
            "status_counts": status_map,
            "new_clients_7d": new_clients_7d,
            "shipments_7d": shipments_7d,
            "shipments_today": shipments_today,
            "total_groups": total_groups,
            "active_groups": active_groups,
            "last_shipments": last_shipments,
            "statuses": tg_models.Shipment.Status.choices,
            "filials": base_models.Filial.objects.filter(is_active=True).order_by("city", "name"),
            "selected_filial": selected_filial,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_shipments_unknown(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial
    q = (request.GET.get("q") or "").strip()
    qs = (
        tg_models.Shipment.objects.select_related("group")
        .filter(user__isnull=True, import_status=tg_models.Shipment.ImportStatus.NO_CLIENT_CODE)
        .order_by("-created_at")
    )
    if staff_filial is not None:
        qs = qs.filter(filial=staff_filial)
    if q:
        qs = qs.filter(Q(tracking_number__icontains=q) | Q(client_code_raw__icontains=q))
    return render(
        request,
        "contacts/manager/shipments_unknown.html",
        {"nav": "shipments", "shipments": qs[:300], "q": q, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
def manager_shipments_client_not_found(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial
    q = (request.GET.get("q") or "").strip()
    qs = (
        tg_models.Shipment.objects.select_related("group")
        .filter(user__isnull=True, import_status=tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND)
        .order_by("-created_at")
    )
    if staff_filial is not None:
        qs = qs.filter(filial=staff_filial)
    if q:
        qs = qs.filter(Q(tracking_number__icontains=q) | Q(client_code_raw__icontains=q))
    return render(
        request,
        "contacts/manager/shipments_client_not_found.html",
        {"nav": "shipments", "shipments": qs[:300], "q": q, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
def manager_shipments_add(request):
    denied = _require_editor_role(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    selected_filial = None
    user = getattr(request, "user", None)
    is_director = _is_director(user) or getattr(user, "is_superuser", False)
    filial_raw = (request.GET.get("filial") or "").strip()
    if is_director and filial_raw:
        try:
            filial_id = int(filial_raw)
        except Exception:
            filial_id = None
        if filial_id:
            selected_filial = base_models.Filial.objects.filter(id=filial_id).first()

    effective_filial = selected_filial if is_director else staff_filial

    return render(
        request,
        "contacts/manager/shipments_add.html",
        {
            "nav": "shipments",
            "filials": base_models.Filial.objects.filter(is_active=True).order_by("city", "name") if is_director else [],
            "selected_filial": selected_filial,
            "effective_filial": effective_filial,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_clients(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    q = (request.GET.get("q") or "").strip()
    qs = tg_models.User.objects.all().order_by("-created_at")
    if staff_filial is not None:
        qs = qs.filter(filial=staff_filial)
    if q:
        qs = qs.filter(
            Q(client_code__icontains=q)
            | Q(full_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(telegram_id__icontains=q)
        )

    clients = qs[:200]
    return render(
        request,
        "contacts/manager/clients.html",
        {"nav": "clients", "clients": clients, "q": q, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
def manager_client_detail(request, user_id: int):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    client = get_object_or_404(tg_models.User, id=user_id)
    if staff_filial is not None and client.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")

    edit_mode = (request.GET.get("edit") or "").strip() == "1"
    form = None
    if request.method == "POST":
        denied_write = _require_editor_role(request)
        if denied_write is not None:
            return denied_write

        if _is_director(getattr(request, "user", None)):
            form = ClientEditDirectorForm(request.POST, instance=client)
            if form.is_valid():
                old_code = (client.client_code or "").strip()
                client = form.save()
                new_code = (getattr(client, "client_code", "") or "").strip()
                if new_code and (new_code != old_code):
                    try:
                        tg_models.attach_orphan_shipments_to_user(client)
                    except Exception:
                        pass
                return redirect("manager_client_detail", user_id=client.id)
            edit_mode = True
        else:
            form = ClientEditManagerForm(request.POST)
            if form.is_valid():
                new_code = (form.cleaned_data.get("client_code") or "").strip() or None
                if new_code and tg_models.User.objects.exclude(id=client.id).filter(client_code__iexact=new_code).exists():
                    form.add_error("client_code", "Код клиента уже используется")
                else:
                    old_code = (client.client_code or "").strip()
                    client.client_code = new_code
                    client.full_name = form.cleaned_data.get("full_name") or ""
                    client.phone = form.cleaned_data.get("phone") or ""
                    client.address = form.cleaned_data.get("address") or ""
                    client.save(update_fields=["client_code", "full_name", "phone", "address", "updated_at"])

                    if new_code and (new_code.strip() != old_code):
                        try:
                            tg_models.attach_orphan_shipments_to_user(client)
                        except Exception:
                            pass
                    return redirect("manager_client_detail", user_id=client.id)
            edit_mode = True
    else:
        if edit_mode:
            if _is_director(getattr(request, "user", None)):
                form = ClientEditDirectorForm(instance=client)
            elif _is_manager(getattr(request, "user", None)):
                form = ClientEditManagerForm(initial={"client_code": client.client_code, "full_name": client.full_name, "phone": client.phone, "address": client.address})
    shipments_qs = tg_models.Shipment.objects.filter(user=client).order_by("-created_at")
    if staff_filial is not None:
        shipments_qs = shipments_qs.filter(filial=staff_filial)
    shipments = shipments_qs[:200]

    delivery_due = Decimal("0")
    try:
        qs_due = tg_models.Shipment.objects.filter(user=client, status=tg_models.Shipment.Status.WAREHOUSE)
        if staff_filial is not None:
            qs_due = qs_due.filter(filial=staff_filial)
        delivery_due = (qs_due.aggregate(s=models.Sum("total_price")).get("s") or Decimal("0"))
    except Exception:
        delivery_due = Decimal("0")

    try:
        debt_value = Decimal(client.total_debt or 0)
    except Exception:
        debt_value = Decimal("0")
    total_due = (delivery_due + debt_value).quantize(Decimal("0.01"))
    return render(
        request,
        "contacts/manager/client_detail.html",
        {
            "nav": "clients",
            "client": client,
            "shipments": shipments,
            "edit_mode": edit_mode,
            "form": form,
            "delivery_due": delivery_due,
            "total_due": total_due,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
@csrf_protect
def manager_client_delete(request, user_id: int):
    denied = _require_director(request)
    if denied is not None:
        return denied
    if request.method != "POST":
        return HttpResponseForbidden("method_not_allowed")

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    client = get_object_or_404(tg_models.User, id=user_id)
    if staff_filial is not None and client.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")
    client.delete()
    return redirect("manager_clients")


@login_required(login_url="/manager/login/")
def manager_groups(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    groups_qs = tg_models.ShipmentGroup.objects.all().order_by("-created_at")
    if staff_filial is not None:
        groups_qs = groups_qs.filter(filial=staff_filial)
    groups = groups_qs[:300]
    return render(request, "contacts/manager/groups.html", {"nav": "groups", "groups": groups, **_role_ctx(request)})


@login_required(login_url="/manager/login/")
def manager_group_detail(request, group_id: int):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
    if staff_filial is not None and group.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")
    shipments_qs = tg_models.Shipment.objects.select_related("user").filter(group=group).order_by("-created_at")
    if staff_filial is not None:
        shipments_qs = shipments_qs.filter(filial=staff_filial)
    shipments = shipments_qs

    has_unsorted = shipments_qs.exclude(status__in=[tg_models.Shipment.Status.WAREHOUSE, tg_models.Shipment.Status.ISSUED]).exists()
    return render(
        request,
        "contacts/manager/group_detail.html",
        {"nav": "groups", "group": group, "shipments": shipments, "has_unsorted": has_unsorted, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
@csrf_protect
def manager_group_sorting(request, group_id: int):
    denied = _require_editor_role(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
    if staff_filial is not None and group.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")
    q = (request.GET.get("q") or "").strip()
    shipment = None
    error = ""
    message = ""

    if q:
        shipment = (
            tg_models.Shipment.objects.select_related("user", "user__filial")
            .filter(group=group, tracking_number__iexact=q)
            .first()
        )
        if shipment is None:
            error = "Товар не найден в этой группе."

    weight_locked = False
    if shipment is not None and _is_manager(getattr(request, "user", None)):
        try:
            weight_locked = bool(shipment.weight_kg and Decimal(str(shipment.weight_kg)) > 0)
        except Exception:
            weight_locked = False

    default_price_per_kg = None
    if shipment is not None:
        try:
            default_price_per_kg = shipment.price_per_kg if shipment.price_per_kg and Decimal(str(shipment.price_per_kg)) > 0 else None
        except Exception:
            default_price_per_kg = None
        if default_price_per_kg is None and shipment.user and shipment.user.filial:
            default_price_per_kg = shipment.user.filial.default_price_per_kg

    if request.method == "POST":
        q_post = (request.POST.get("tracking_number") or request.POST.get("q") or "").strip()
        q = q_post or q
        if not q:
            return redirect("manager_group_sorting", group_id=group.id)

        shipment = (
            tg_models.Shipment.objects.select_related("user", "user__filial")
            .filter(group=group, tracking_number__iexact=q)
            .first()
        )
        if shipment is None:
            return render(
                request,
                "contacts/manager/group_sorting.html",
                {
                    "nav": "groups",
                    "group": group,
                    "q": q,
                    "shipment": None,
                    "error": "Товар не найден в этой группе.",
                    "message": "",
                    "default_price_per_kg": None,
                    "weight_locked": False,
                    **_role_ctx(request),
                },
            )

        weight_locked = False
        if shipment is not None and _is_manager(getattr(request, "user", None)):
            try:
                weight_locked = bool(shipment.weight_kg and Decimal(str(shipment.weight_kg)) > 0)
            except Exception:
                weight_locked = False
            if weight_locked:
                default_price_per_kg = None
                try:
                    default_price_per_kg = shipment.price_per_kg if shipment.price_per_kg and Decimal(str(shipment.price_per_kg)) > 0 else None
                except Exception:
                    default_price_per_kg = None
                return render(
                    request,
                    "contacts/manager/group_sorting.html",
                    {
                        "nav": "groups",
                        "group": group,
                        "q": q,
                        "shipment": shipment,
                        "error": "Вес уже установлен. Менеджер может указать вес только один раз.",
                        "message": "",
                        "default_price_per_kg": default_price_per_kg,
                        "weight_locked": True,
                        **_role_ctx(request),
                    },
                )

        pricing_mode = (request.POST.get("pricing_mode") or "kg").strip()
        if pricing_mode not in {"kg", "gabarit"}:
            pricing_mode = "kg"

        weight = None
        raw_w = (request.POST.get("weight_kg") or "").replace(",", ".").strip()
        if raw_w:
            try:
                weight = Decimal(raw_w)
            except InvalidOperation:
                weight = None

        if pricing_mode == "kg":
            if weight is None or weight <= 0:
                error = "Укажите вес."
            else:
                price_per_kg_value = None
                try:
                    price_per_kg_value = shipment.price_per_kg if shipment.price_per_kg and Decimal(str(shipment.price_per_kg)) > 0 else None
                except Exception:
                    price_per_kg_value = None
                if price_per_kg_value is None and shipment.user and shipment.user.filial:
                    price_per_kg_value = shipment.user.filial.default_price_per_kg

                if price_per_kg_value is None:
                    error = "Не задана цена за кг в филиале клиента (default_price_per_kg)."
                else:
                    with transaction.atomic():
                        shipment.pricing_mode = tg_models.Shipment.PricingMode.KG
                        shipment.weight_kg = weight
                        shipment.price_per_kg = price_per_kg_value
                        shipment.total_price = (weight * price_per_kg_value).quantize(Decimal("0.01"))
                        shipment.status = tg_models.Shipment.Status.WAREHOUSE
                        shipment.arrival_date = timezone.now().date()
                        shipment.save(update_fields=["pricing_mode", "weight_kg", "price_per_kg", "total_price", "status", "arrival_date", "updated_at"])

                        remaining_unsorted = tg_models.Shipment.objects.filter(group=group)
                        if staff_filial is not None:
                            remaining_unsorted = remaining_unsorted.filter(filial=staff_filial)
                        remaining_unsorted = remaining_unsorted.exclude(
                            status__in=[tg_models.Shipment.Status.WAREHOUSE, tg_models.Shipment.Status.ISSUED]
                        ).exists()

                        if (not remaining_unsorted) and group.status != tg_models.ShipmentGroup.Status.WAREHOUSE:
                            group.status = tg_models.ShipmentGroup.Status.WAREHOUSE
                            group.save(update_fields=["status", "updated_at"])

                    if shipment.user and getattr(shipment.user, "telegram_id", None):
                        token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
                        if token:
                            text = _shipment_notify_text_ready_for_pickup(
                                tracking=shipment.tracking_number,
                                weight_kg=shipment.weight_kg,
                                total_price=shipment.total_price,
                            )
                            try:
                                _send_telegram_message(token=token, chat_id=int(shipment.user.telegram_id), text=text)
                            except Exception:
                                pass

                    return redirect("manager_group_sorting", group_id=group.id)
        else:
            raw_total = (request.POST.get("total_price") or "").replace(",", ".").strip()
            if not raw_total:
                error = "Укажите стоимость (итого)."
            else:
                try:
                    total_price_value = Decimal(raw_total)
                except InvalidOperation:
                    total_price_value = None

                if total_price_value is None or total_price_value <= 0:
                    error = "Некорректная стоимость (итого)."
                else:
                    price_per_kg_value = None
                    try:
                        price_per_kg_value = shipment.price_per_kg if shipment.price_per_kg and Decimal(str(shipment.price_per_kg)) > 0 else None
                    except Exception:
                        price_per_kg_value = None
                    if price_per_kg_value is None and shipment.user and shipment.user.filial:
                        price_per_kg_value = shipment.user.filial.default_price_per_kg

                    with transaction.atomic():
                        shipment.pricing_mode = tg_models.Shipment.PricingMode.GABARIT
                        if weight is not None and weight > 0:
                            shipment.weight_kg = weight
                        shipment.price_per_kg = price_per_kg_value or Decimal("0")
                        shipment.total_price = total_price_value.quantize(Decimal("0.01"))
                        shipment.status = tg_models.Shipment.Status.WAREHOUSE
                        shipment.arrival_date = timezone.now().date()
                        shipment.save(update_fields=["pricing_mode", "weight_kg", "price_per_kg", "total_price", "status", "arrival_date", "updated_at"])

                        remaining_unsorted = tg_models.Shipment.objects.filter(group=group)
                        if staff_filial is not None:
                            remaining_unsorted = remaining_unsorted.filter(filial=staff_filial)
                        remaining_unsorted = remaining_unsorted.exclude(
                            status__in=[tg_models.Shipment.Status.WAREHOUSE, tg_models.Shipment.Status.ISSUED]
                        ).exists()

                        if (not remaining_unsorted) and group.status != tg_models.ShipmentGroup.Status.WAREHOUSE:
                            group.status = tg_models.ShipmentGroup.Status.WAREHOUSE
                            group.save(update_fields=["status", "updated_at"])

                    if shipment.user and getattr(shipment.user, "telegram_id", None):
                        token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
                        if token:
                            text = _shipment_notify_text_ready_for_pickup(
                                tracking=shipment.tracking_number,
                                weight_kg=shipment.weight_kg,
                                total_price=shipment.total_price,
                            )
                            try:
                                _send_telegram_message(token=token, chat_id=int(shipment.user.telegram_id), text=text)
                            except Exception:
                                pass

                    return redirect("manager_group_sorting", group_id=group.id)

        default_price_per_kg = None
        if shipment is not None:
            try:
                default_price_per_kg = shipment.price_per_kg if shipment.price_per_kg and Decimal(str(shipment.price_per_kg)) > 0 else None
            except Exception:
                default_price_per_kg = None

    return render(
        request,
        "contacts/manager/group_sorting.html",
        {
            "nav": "groups",
            "group": group,
            "q": q,
            "shipment": shipment,
            "error": error,
            "message": message,
            "default_price_per_kg": default_price_per_kg,
            "weight_locked": weight_locked,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
@csrf_protect
def manager_group_set_bishkek(request, group_id: int):
    denied = _require_editor_role(request)
    if denied is not None:
        return denied
    if request.method != "POST":
        return HttpResponseForbidden("method_not_allowed")

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
    if staff_filial is not None and group.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")
    group.status = tg_models.ShipmentGroup.Status.BISHKEK
    group.bishkek_marked = True
    group.save(update_fields=["status", "bishkek_marked", "updated_at"])

    qs_update = tg_models.Shipment.objects.filter(group=group)
    if staff_filial is not None:
        qs_update = qs_update.filter(filial=staff_filial)
    qs_update.update(status=tg_models.Shipment.Status.BISHKEK, updated_at=timezone.now())

    token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
    if token:
        qs = tg_models.Shipment.objects.select_related("user").filter(group=group, user__isnull=False)
        if staff_filial is not None:
            qs = qs.filter(filial=staff_filial)
        for sh in qs:
            user_obj = sh.user
            chat_id = getattr(user_obj, "telegram_id", None)
            if not chat_id:
                continue
            try:
                _send_telegram_message(
                    token=token,
                    chat_id=int(chat_id),
                    text=_shipment_notify_text_bishkek(tracking=sh.tracking_number),
                )
            except Exception:
                continue

    return redirect("manager_group_detail", group_id=group.id)


@login_required(login_url="/manager/login/")
@csrf_protect
def manager_group_shipment_set_issued(request, group_id: int, shipment_id: int):
    denied = _require_editor_role(request)
    if denied is not None:
        return denied
    if request.method != "POST":
        return HttpResponseForbidden("method_not_allowed")

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
    if staff_filial is not None and group.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")
    shipment = get_object_or_404(tg_models.Shipment.objects.select_related("user"), id=shipment_id, group=group)
    if staff_filial is not None and shipment.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")

    if shipment.status != tg_models.Shipment.Status.WAREHOUSE:
        return HttpResponseForbidden("not_ready_for_pickup")

    if shipment.status != tg_models.Shipment.Status.ISSUED:
        shipment.status = tg_models.Shipment.Status.ISSUED
        shipment.save(update_fields=["status", "updated_at"])

        if shipment.user and getattr(shipment.user, "telegram_id", None):
            token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
            if token:
                text = _shipment_notify_text_issued(tracking=shipment.tracking_number)
                try:
                    _send_telegram_message(token=token, chat_id=int(shipment.user.telegram_id), text=text)
                except Exception:
                    pass

    all_qs = tg_models.Shipment.objects.filter(group=group)
    if staff_filial is not None:
        all_qs = all_qs.filter(filial=staff_filial)
    all_issued = not all_qs.exclude(status=tg_models.Shipment.Status.ISSUED).exists()
    if all_issued and group.status != tg_models.ShipmentGroup.Status.ISSUED:
        group.status = tg_models.ShipmentGroup.Status.ISSUED
        group.save(update_fields=["status", "updated_at"])

    return redirect("manager_group_detail", group_id=group.id)


@login_required(login_url="/manager/login/")
def manager_shipments(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    status_tabs = [
        ("", "Все"),
        (tg_models.Shipment.Status.ON_THE_WAY, "В пути"),
        (tg_models.Shipment.Status.BISHKEK, "В Бишкеке"),
        (tg_models.Shipment.Status.WAREHOUSE, "Готов к выдаче"),
        (tg_models.Shipment.Status.ISSUED, "Выдано"),
    ]
    allowed_statuses = {v for v, _ in status_tabs if v}
    if status and status not in allowed_statuses:
        status = ""

    qs = (
        tg_models.Shipment.objects.select_related("user")
        .filter(user__isnull=False, import_status=tg_models.Shipment.ImportStatus.OK)
        .order_by("-created_at")
    )
    if staff_filial is not None:
        qs = qs.filter(filial=staff_filial)
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(tracking_number__icontains=q)
            | Q(client_code_raw__icontains=q)
            | Q(user__client_code__icontains=q)
            | Q(user__full_name__icontains=q)
            | Q(user__phone__icontains=q)
        )

    shipments = qs[:300]
    return render(
        request,
        "contacts/manager/shipments.html",
        {
            "nav": "shipments",
            "shipments": shipments,
            "q": q,
            "status": status,
            "status_tabs": status_tabs,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_analytics(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    selected_filial = None
    is_director = _is_director(getattr(request, "user", None)) or getattr(getattr(request, "user", None), "is_superuser", False)
    filial_raw = (request.GET.get("filial") or "").strip()
    if is_director and filial_raw:
        try:
            filial_id = int(filial_raw)
        except Exception:
            filial_id = None
        if filial_id:
            selected_filial = base_models.Filial.objects.filter(id=filial_id).first()

    effective_filial = selected_filial if is_director else staff_filial

    today = timezone.localdate()
    month_raw = (request.GET.get("month") or "").strip()  # YYYY-MM
    day_raw = (request.GET.get("day") or "").strip()  # YYYY-MM-DD

    if month_raw:
        try:
            month_date = timezone.datetime.fromisoformat(month_raw + "-01").date()
        except Exception:
            month_date = today.replace(day=1)
    else:
        month_date = today.replace(day=1)

    selected_day = None
    if day_raw:
        try:
            selected_day = timezone.datetime.fromisoformat(day_raw).date()
        except Exception:
            selected_day = None

    # month boundaries
    first_day = month_date.replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1, day=1)

    prev_month = (first_day - timezone.timedelta(days=1)).replace(day=1)

    dec0 = Value(Decimal("0.00"), output_field=DecimalField(max_digits=18, decimal_places=2))
    delivery_expr = Coalesce(F("total_price"), dec0)
    amount_expr = ExpressionWrapper(
        delivery_expr,
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    base_qs = tg_models.Shipment.objects.select_related("user").filter(
        status=tg_models.Shipment.Status.ISSUED,
        updated_at__date__gte=first_day,
        updated_at__date__lt=next_month,
    )
    if effective_filial is not None:
        base_qs = base_qs.filter(filial=effective_filial)

    per_day_rows = (
        base_qs.annotate(d=TruncDate("updated_at"))
        .values("d")
        .annotate(
            cnt=Count("id"),
            total=Coalesce(Sum(amount_expr, output_field=DecimalField(max_digits=18, decimal_places=2)), dec0),
        )
        .order_by("d")
    )

    day_map = {row["d"]: {"cnt": row["cnt"], "total": row["total"]} for row in per_day_rows}

    if selected_day is None:
        selected_day = today if (today >= first_day and today < next_month) else first_day

    day_ops_qs = tg_models.Shipment.objects.select_related("user").filter(
        status=tg_models.Shipment.Status.ISSUED,
        updated_at__date=selected_day,
    )
    if effective_filial is not None:
        day_ops_qs = day_ops_qs.filter(filial=effective_filial)
    day_ops = day_ops_qs.annotate(amount=amount_expr).order_by("-updated_at")[:500]

    selected_breakdown = day_ops_qs.aggregate(
        delivery=Coalesce(Sum(delivery_expr, output_field=DecimalField(max_digits=18, decimal_places=2)), dec0),
        total=Coalesce(Sum(amount_expr, output_field=DecimalField(max_digits=18, decimal_places=2)), dec0),
        cnt=Count("id"),
    )

    office_qs = tg_models.Shipment.objects.select_related("user").filter(
        status=tg_models.Shipment.Status.WAREHOUSE,
    )
    if effective_filial is not None:
        office_qs = office_qs.filter(filial=effective_filial)

    office_stats = office_qs.aggregate(
        cnt=Count("id"),
        clients=Count("user_id", distinct=True),
        delivery=Coalesce(Sum(delivery_expr, output_field=DecimalField(max_digits=18, decimal_places=2)), dec0),
        total=Coalesce(Sum(amount_expr, output_field=DecimalField(max_digits=18, decimal_places=2)), dec0),
    )

    selected_meta = day_map.get(selected_day) or {"cnt": 0, "total": 0}

    calendar_cells = []
    # start from Monday
    start = first_day - timezone.timedelta(days=first_day.weekday())
    cur = start
    while cur < next_month or cur.weekday() != 0:
        is_current_month = (cur.month == first_day.month and cur.year == first_day.year)
        meta = day_map.get(cur)
        calendar_cells.append(
            {
                "date": cur,
                "in_month": is_current_month,
                "cnt": (meta or {}).get("cnt", 0),
                "total": (meta or {}).get("total", 0),
                "is_selected": (cur == selected_day),
            }
        )
        cur = cur + timezone.timedelta(days=1)
        if cur >= next_month and cur.weekday() == 0:
            break

    return render(
        request,
        "contacts/manager/analytics.html",
        {
            "nav": "analytics",
            "month": first_day,
            "prev_month": prev_month,
            "next_month": next_month,
            "selected_day": selected_day,
            "selected_cnt": selected_meta.get("cnt", 0),
            "selected_total": selected_meta.get("total", 0),
            "selected_delivery": selected_breakdown.get("delivery", 0),
            "selected_penalty": 0,
            "office_cnt": office_stats.get("cnt", 0),
            "office_clients": office_stats.get("clients", 0),
            "office_delivery": office_stats.get("delivery", 0),
            "office_penalty": 0,
            "office_total": office_stats.get("total", 0),
            "calendar_cells": calendar_cells,
            "day_ops": day_ops,
            "filials": base_models.Filial.objects.filter(is_active=True).order_by("city", "name") if is_director else [],
            "selected_filial": selected_filial,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_penalties(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    today = timezone.localdate()
    free_days = 3

    selected_filial = None
    is_director = _is_director(getattr(request, "user", None)) or getattr(getattr(request, "user", None), "is_superuser", False)
    filial_raw = (request.GET.get("filial") or "").strip()
    if is_director and filial_raw:
        try:
            filial_id = int(filial_raw)
        except Exception:
            filial_id = None
        if filial_id:
            selected_filial = base_models.Filial.objects.filter(id=filial_id).first()

    effective_filial = selected_filial if is_director else staff_filial

    qs = (
        tg_models.Shipment.objects.select_related("user", "user__filial")
        .filter(status=tg_models.Shipment.Status.WAREHOUSE)
        .exclude(user__isnull=True)
        .exclude(arrival_date__isnull=True)
    )

    candidates = {}
    for sh in qs.iterator():
        user_obj = sh.user
        if not user_obj:
            continue
        filial_obj = getattr(user_obj, "filial", None)
        if filial_obj is None:
            continue
        if effective_filial is not None and getattr(filial_obj, "id", None) != getattr(effective_filial, "id", None):
            continue

        per_day = getattr(filial_obj, "storage_penalty_per_day", None)
        if per_day is None:
            continue
        try:
            per_day = Decimal(per_day)
        except Exception:
            continue
        if per_day <= 0:
            continue

        arrived = sh.arrival_date
        free_until = arrived + timezone.timedelta(days=free_days)
        if today <= free_until:
            continue

        existing = candidates.get(user_obj.id)
        if not existing or free_until < existing["free_until"]:
            candidates[user_obj.id] = {"user": user_obj, "filial": filial_obj, "per_day": per_day, "free_until": free_until}

    rows = []
    for item in candidates.values():
        user_obj = item["user"]
        filial_obj = item["filial"]
        per_day = item["per_day"]
        free_until = item["free_until"]

        last = getattr(user_obj, "storage_penalty_last_charged_date", None)
        start_date = max(last or free_until, free_until)
        if start_date >= today:
            continue
        days_to_charge = (today - start_date).days
        if days_to_charge <= 0:
            continue
        to_charge = (Decimal(days_to_charge) * per_day).quantize(Decimal("0.01"))
        if to_charge <= 0:
            continue

        days_overdue = (today - free_until).days
        if days_overdue < 0:
            days_overdue = 0

        rows.append(
            {
                "id": user_obj.id,
                "user": user_obj,
                "filial": filial_obj,
                "days_overdue": days_overdue,
                "to_charge": to_charge,
                "storage_penalty_total": getattr(user_obj, "storage_penalty_total", 0) or 0,
                "storage_penalty_last_charged_date": getattr(user_obj, "storage_penalty_last_charged_date", None),
            }
        )

    rows.sort(key=lambda r: (-(r.get("days_overdue") or 0), str(getattr(r.get("user"), "client_code", "") or "")))

    return render(
        request,
        "contacts/manager/penalties.html",
        {
            "nav": "penalties",
            "today": today,
            "free_days": free_days,
            "rows": rows,
            "filials": base_models.Filial.objects.filter(is_active=True).order_by("city", "name") if is_director else [],
            "selected_filial": selected_filial,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_shipments_import(request):
    denied = _require_editor_role(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    selected_filial = None
    user = getattr(request, "user", None)
    is_director = _is_director(user) or getattr(user, "is_superuser", False)
    filial_raw = (request.GET.get("filial") or "").strip()
    if is_director:
        if not filial_raw:
            return redirect("manager_shipments_add")
        try:
            filial_id = int(filial_raw)
        except Exception:
            filial_id = None
        if filial_id:
            selected_filial = base_models.Filial.objects.filter(id=filial_id).first()
        if selected_filial is None:
            return redirect("manager_shipments_add")

    effective_filial = selected_filial if is_director else staff_filial

    if load_workbook is None:
        return render(
            request,
            "contacts/manager/shipments_import.html",
            {
                "nav": "shipments",
                "form": ShipmentImportForm(initial={"group_status": tg_models.ShipmentGroup.Status.ON_THE_WAY}),
                "report": {"error": "openpyxl не установлен. Установите зависимости."},
            },
        )

    def _next_group_name() -> str:
        with transaction.atomic():
            last = tg_models.ShipmentGroup.objects.select_for_update().order_by("-id").first()
            next_n = 1 if last is None else int(last.id) + 1
            return f"group-{next_n}"

    def _settings_token() -> str:
        s = base_models.Settings.objects.first()
        return (getattr(s, "telegram_token", "") or "").strip()

    def _notify_user_arrival(user_obj: tg_models.User, tracking: str, shipment_status: str) -> None:
        token = _settings_token()
        if not token:
            return
        chat_id = getattr(user_obj, "telegram_id", None)
        if not chat_id:
            return
        if shipment_status == tg_models.Shipment.Status.WAREHOUSE:
            text = _shipment_notify_text_ready_for_pickup(tracking=tracking)
        elif shipment_status == tg_models.Shipment.Status.ON_THE_WAY:
            text = _shipment_notify_text_in_transit(tracking=tracking)
        else:
            text = _shipment_notify_text_bishkek(tracking=tracking)
        try:
            _send_telegram_message(token=token, chat_id=int(chat_id), text=text)
        except Exception:
            return

    def _looks_like_tracking(value: str) -> bool:
        v = (value or "").strip()
        if not v:
            return False
        if len(v) < 6:
            return False
        has_digit = any(ch.isdigit() for ch in v)
        if not has_digit:
            return False
        # Skip header/notes rows like "Трек-код товара" or other Cyrillic text
        has_cyrillic = any(("а" <= ch.lower() <= "я") or (ch.lower() == "ё") for ch in v)
        if has_cyrillic:
            return False
        return True

    def _normalize_import_client_code(raw_code: str) -> str:
        code = (raw_code or "").strip()
        if not code:
            return ""
        if "-" in code:
            return code.upper()
        prefix = (getattr(effective_filial, "client_code_prefix", "") or "").strip().upper() if effective_filial else ""
        if not prefix:
            return code
        return f"{prefix}-{code}"

    def _find_user_by_client_code(raw_code: str) -> tg_models.User | None:
        code = _normalize_import_client_code(raw_code)
        if not code:
            return None

        qs_base = tg_models.User.objects.all()
        if effective_filial is not None:
            qs_base = qs_base.filter(filial=effective_filial)

        user_obj = qs_base.filter(client_code__iexact=code).first()
        if user_obj:
            return user_obj

        if "-" in code:
            return None

        suffix = f"-{code}"
        qs = qs_base.filter(client_code__iendswith=suffix)
        if qs.count() == 1:
            return qs.first()
        return None

    report = None
    preview_rows = None
    preview_summary = None
    preview_key = "manager_shipments_import_preview"

    PREVIEW_LIMIT = 200
    BULK_SIZE = 500
    MAX_NOTIFY = 200

    def _cleanup_tmp(path_value: str | None) -> None:
        p = (path_value or "").strip()
        if not p:
            return
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            return

    def _tmp_xlsx_path() -> str:
        return os.path.join(tempfile.gettempdir(), f"cargobot_import_{uuid.uuid4().hex}.xlsx")

    if request.method == "POST":
        action = (request.POST.get("action") or "preview").strip()
        if action == "save":
            payload = request.session.get(preview_key) or {}
            tmp_path = (payload.get("tmp_path") or "").strip()
            group_status = payload.get("group_status")
            sent_date_raw = (payload.get("sent_date") or "").strip()
            sent_date = None
            if sent_date_raw:
                try:
                    sent_date = timezone.datetime.fromisoformat(sent_date_raw).date()
                except Exception:
                    sent_date = None
            price_per_kg = payload.get("price_per_kg")

            if not tmp_path or (not os.path.exists(tmp_path)):
                report = {"error": "Файл не найден. Нажмите 'Проверить' и попробуйте снова."}
                form = ShipmentImportForm(initial={"sent_date": sent_date, "group_status": tg_models.ShipmentGroup.Status.ON_THE_WAY})
            else:
                created = 0
                skipped = 0
                errors: list[dict] = []

                notify_count = 0
                to_create: list[tg_models.Shipment] = []

                users_qs = tg_models.User.objects.all()
                if effective_filial is not None:
                    users_qs = users_qs.filter(filial=effective_filial)
                users_qs = users_qs.exclude(client_code__isnull=True).exclude(client_code="")

                code_map = {str(u.client_code).strip().upper(): u for u in users_qs}
                suffix_map = {}
                for u in users_qs:
                    cc = str(u.client_code or "").strip()
                    if "-" not in cc:
                        continue
                    try:
                        suf = cc.split("-", 1)[1].strip()
                    except Exception:
                        continue
                    if not suf:
                        continue
                    if suf in suffix_map and suffix_map[suf] is not None:
                        suffix_map[suf] = None
                    else:
                        suffix_map[suf] = u

                def _resolve_user_for_code(raw_code: str) -> tg_models.User | None:
                    code_norm = _normalize_import_client_code(raw_code)
                    if code_norm:
                        u = code_map.get(code_norm.strip().upper())
                        if u is not None:
                            return u
                    code_raw = (raw_code or "").strip()
                    if code_raw and "-" not in code_raw:
                        u2 = suffix_map.get(code_raw)
                        if u2 is not None:
                            return u2
                    return None

                def _flush(group_obj: tg_models.ShipmentGroup) -> None:
                    nonlocal to_create, created, skipped
                    if not to_create:
                        return
                    trackings = [s.tracking_number for s in to_create if s.tracking_number]
                    existing = set()
                    if trackings:
                        exists_qs = tg_models.Shipment.objects.filter(tracking_number__in=trackings)
                        if effective_filial is not None:
                            exists_qs = exists_qs.filter(filial=effective_filial)
                        existing = set(exists_qs.values_list("tracking_number", flat=True))
                    final = []
                    for s in to_create:
                        if s.tracking_number and s.tracking_number in existing:
                            skipped += 1
                            continue
                        final.append(s)
                    if final:
                        tg_models.Shipment.objects.bulk_create(final, batch_size=BULK_SIZE)
                        created += len(final)
                    to_create = []
                with transaction.atomic():
                    group_obj = tg_models.ShipmentGroup.objects.create(
                        name=_next_group_name(),
                        status=group_status or tg_models.ShipmentGroup.Status.ON_THE_WAY,
                        sent_date=sent_date,
                        filial=effective_filial,
                    )

                    try:
                        wb = load_workbook(filename=tmp_path, read_only=True, data_only=True)
                        ws = wb.active
                        for idx, row in enumerate(ws.iter_rows(min_row=1, values_only=True), start=1):
                            tracking = str((row[0] if len(row) > 0 else "") or "").strip()
                            raw_code = str((row[1] if len(row) > 1 else "") or "").strip()

                            if not tracking and not raw_code:
                                continue
                            if tracking and not _looks_like_tracking(tracking):
                                continue

                            if not tracking:
                                skipped += 1
                                continue

                            user_obj = None
                            import_status = tg_models.Shipment.ImportStatus.OK
                            client_code_to_store = _normalize_import_client_code(raw_code)

                            if not raw_code:
                                import_status = tg_models.Shipment.ImportStatus.NO_CLIENT_CODE
                            else:
                                user_obj = _resolve_user_for_code(raw_code)
                                if user_obj is None:
                                    import_status = tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND

                            sh = tg_models.Shipment(
                                filial=effective_filial,
                                user=user_obj,
                                group=group_obj,
                                tracking_number=tracking,
                                status=group_obj.status or tg_models.Shipment.Status.ON_THE_WAY,
                                client_code_raw=client_code_to_store or raw_code,
                                import_status=import_status,
                            )
                            if price_per_kg is not None and price_per_kg != "":
                                try:
                                    sh.price_per_kg = price_per_kg
                                except Exception:
                                    pass
                            to_create.append(sh)
                            if len(to_create) >= BULK_SIZE:
                                _flush(group_obj)

                            if user_obj is not None and import_status == tg_models.Shipment.ImportStatus.OK and notify_count < MAX_NOTIFY:
                                _notify_user_arrival(user_obj=user_obj, tracking=tracking, shipment_status=sh.status)
                                notify_count += 1

                        _flush(group_obj)
                    finally:
                        pass

                _cleanup_tmp(tmp_path)
                request.session.pop(preview_key, None)
                return redirect("manager_group_detail", group_id=group_obj.id)
        else:
            form = ShipmentImportForm(request.POST, request.FILES)
            if form.is_valid():
                prev_payload = request.session.get(preview_key) or {}
                _cleanup_tmp((prev_payload.get("tmp_path") or "").strip())
                sent_date = form.cleaned_data.get("sent_date")
                group_status = form.cleaned_data.get("group_status")
                price_per_kg = form.cleaned_data.get("price_per_kg")
                f = form.cleaned_data.get("file")

                tmp_path = _tmp_xlsx_path()
                try:
                    with open(tmp_path, "wb") as out:
                        for chunk in f.chunks():
                            out.write(chunk)
                except Exception as e:
                    report = {"error": str(e)}
                else:
                    rows: list[dict] = []
                    ok_cnt = 0
                    no_client_code_cnt = 0
                    client_not_found_cnt = 0

                    try:
                        wb = load_workbook(filename=tmp_path, read_only=True, data_only=True)
                        ws = wb.active
                        for idx, row in enumerate(ws.iter_rows(min_row=1, values_only=True), start=1):
                            tracking = str((row[0] if len(row) > 0 else "") or "").strip()
                            client_code = str((row[1] if len(row) > 1 else "") or "").strip()
                            if not tracking and not client_code:
                                continue
                            if tracking and not _looks_like_tracking(tracking):
                                continue

                            if len(rows) >= PREVIEW_LIMIT:
                                continue

                            if not client_code:
                                no_client_code_cnt += 1
                                rows.append({
                                    "row": idx,
                                    "tracking": tracking,
                                    "client_code": "",
                                    "user_id": None,
                                    "user_name": "",
                                    "import_status": tg_models.Shipment.ImportStatus.NO_CLIENT_CODE,
                                })
                                continue

                            normalized_code = _normalize_import_client_code(client_code)
                            user_obj = _find_user_by_client_code(client_code)
                            if not user_obj:
                                client_not_found_cnt += 1
                                rows.append({
                                    "row": idx,
                                    "tracking": tracking,
                                    "client_code": normalized_code or client_code,
                                    "user_id": None,
                                    "user_name": "",
                                    "import_status": tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND,
                                })
                                continue

                            ok_cnt += 1
                            rows.append({
                                "row": idx,
                                "tracking": tracking,
                                "client_code": normalized_code or client_code,
                                "user_id": user_obj.id,
                                "user_name": getattr(user_obj, "full_name", "") or getattr(user_obj, "client_code", ""),
                                "import_status": tg_models.Shipment.ImportStatus.OK,
                            })
                    except Exception as e:
                        _cleanup_tmp(tmp_path)
                        report = {"error": str(e)}
                    else:
                        request.session[preview_key] = {
                            "sent_date": sent_date.isoformat() if sent_date else "",
                            "group_status": group_status,
                            "price_per_kg": str(price_per_kg) if price_per_kg is not None else "",
                            "tmp_path": tmp_path,
                        }
                        preview_rows = rows
                        preview_summary = {
                            "total": len(rows),
                            "ok": ok_cnt,
                            "no_client_code": no_client_code_cnt,
                            "client_not_found": client_not_found_cnt,
                            "preview_limit": PREVIEW_LIMIT,
                        }
                        report = {"errors": []}
            else:
                report = {"error": "Проверьте форму. Есть ошибки."}
    else:
        form = ShipmentImportForm(initial={"group_status": tg_models.ShipmentGroup.Status.ON_THE_WAY})

    return render(
        request,
        "contacts/manager/shipments_import.html",
        {
            "nav": "shipments",
            "form": form,
            "report": report,
            "preview_rows": preview_rows,
            "preview_summary": preview_summary,
            "selected_filial": selected_filial,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_shipment_new(request):
    denied = _require_editor_role(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    selected_filial = None
    user = getattr(request, "user", None)
    is_director = _is_director(user) or getattr(user, "is_superuser", False)
    filial_raw = (request.GET.get("filial") or "").strip()
    if is_director:
        if not filial_raw:
            return redirect("manager_shipments_add")
        try:
            filial_id = int(filial_raw)
        except Exception:
            filial_id = None
        if filial_id:
            selected_filial = base_models.Filial.objects.filter(id=filial_id).first()
        if selected_filial is None:
            return redirect("manager_shipments_add")

    effective_filial = selected_filial if is_director else staff_filial

    if request.method == "POST":
        form = ShipmentCreateForm(request.POST, staff_filial=effective_filial)
        if form.is_valid():
            shipment = form.save(staff_filial=effective_filial)
            return redirect("manager_shipment_detail", shipment_id=shipment.id)
    else:
        form = ShipmentCreateForm(staff_filial=effective_filial)

    return render(
        request,
        "contacts/manager/shipment_new.html",
        {"nav": "shipments", "form": form, "selected_filial": selected_filial, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
def manager_shipment_detail(request, shipment_id: int):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    shipment = get_object_or_404(tg_models.Shipment.objects.select_related("user"), id=shipment_id)
    if staff_filial is not None and shipment.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")

    if request.method == "POST":
        denied_write = _require_director(request)
        if denied_write is not None:
            return denied_write
        status = (request.POST.get("status") or "").strip()
        weight_kg = (request.POST.get("weight_kg") or "").strip()
        price_per_kg = (request.POST.get("price_per_kg") or "").strip()
        total_price = (request.POST.get("total_price") or "").strip()
        arrival_date = (request.POST.get("arrival_date") or "").strip()

        if status and status in dict(tg_models.Shipment.Status.choices):
            shipment.status = status
        if weight_kg:
            shipment.weight_kg = weight_kg
        if price_per_kg:
            shipment.price_per_kg = price_per_kg
        if total_price:
            shipment.total_price = total_price
        if arrival_date:
            try:
                shipment.arrival_date = timezone.datetime.fromisoformat(arrival_date).date()
            except Exception:
                pass

        shipment.save()
        return redirect("manager_shipment_detail", shipment_id=shipment.id)

    return render(
        request,
        "contacts/manager/shipment_detail.html",
        {"nav": "shipments", "shipment": shipment, "statuses": tg_models.Shipment.Status.choices, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
@csrf_protect
def manager_shipment_delete(request, shipment_id: int):
    denied = _require_director(request)
    if denied is not None:
        return denied
    if request.method != "POST":
        return HttpResponseForbidden("method_not_allowed")

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    shipment = get_object_or_404(tg_models.Shipment, id=shipment_id)
    if staff_filial is not None and shipment.filial_id != staff_filial.id:
        return HttpResponseForbidden("Нет доступа")
    shipment.delete()
    return redirect("manager_shipments")
