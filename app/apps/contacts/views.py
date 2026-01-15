from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from decimal import Decimal, InvalidOperation
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

    shipments_qs = tg_models.Shipment.objects.all()
    users_qs = tg_models.User.objects.all()
    groups_qs = tg_models.ShipmentGroup.objects.all()
    if staff_filial is not None:
        shipments_qs = shipments_qs.filter(filial=staff_filial)
        users_qs = users_qs.filter(filial=staff_filial)
        groups_qs = groups_qs.filter(filial=staff_filial)

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
    qs = (
        tg_models.Shipment.objects.select_related("group")
        .filter(user__isnull=True, import_status=tg_models.Shipment.ImportStatus.NO_CLIENT_CODE)
        .order_by("-created_at")
    )
    if staff_filial is not None:
        qs = qs.filter(filial=staff_filial)
    return render(
        request,
        "contacts/manager/shipments_unknown.html",
        {"nav": "shipments", "shipments": qs[:300], **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
def manager_shipments_client_not_found(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial
    qs = (
        tg_models.Shipment.objects.select_related("group")
        .filter(user__isnull=True, import_status=tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND)
        .order_by("-created_at")
    )
    if staff_filial is not None:
        qs = qs.filter(filial=staff_filial)
    return render(
        request,
        "contacts/manager/shipments_client_not_found.html",
        {"nav": "shipments", "shipments": qs[:300], **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
def manager_shipments_add(request):
    denied = _require_manager_role(request)
    if denied is not None:
        return denied
    return render(request, "contacts/manager/shipments_add.html", {"nav": "shipments", **_role_ctx(request)})


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
                form.save()
                return redirect("manager_client_detail", user_id=client.id)
            edit_mode = True
        else:
            form = ClientEditManagerForm(request.POST)
            if form.is_valid():
                new_code = (form.cleaned_data.get("client_code") or "").strip() or None
                if new_code and tg_models.User.objects.exclude(id=client.id).filter(client_code__iexact=new_code).exists():
                    form.add_error("client_code", "Код клиента уже используется")
                else:
                    client.client_code = new_code
                    client.full_name = form.cleaned_data.get("full_name") or ""
                    client.phone = form.cleaned_data.get("phone") or ""
                    client.address = form.cleaned_data.get("address") or ""
                    client.save(update_fields=["client_code", "full_name", "phone", "address", "updated_at"])
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

        raw_w = (request.POST.get("weight_kg") or "").replace(",", ".").strip()
        if not raw_w:
            error = "Укажите вес."
        else:
            try:
                weight = Decimal(raw_w)
            except InvalidOperation:
                weight = None
            if weight is None or weight <= 0:
                error = "Некорректный вес."
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
                        shipment.weight_kg = weight
                        shipment.price_per_kg = price_per_kg_value
                        shipment.total_price = (weight * price_per_kg_value).quantize(Decimal("0.01"))
                        shipment.status = tg_models.Shipment.Status.WAREHOUSE
                        shipment.arrival_date = timezone.now().date()
                        shipment.save(update_fields=["weight_kg", "price_per_kg", "total_price", "status", "arrival_date", "updated_at"])

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
    amount_expr = ExpressionWrapper(
        Coalesce(F("total_price"), dec0) + Coalesce(F("storage_penalty_total"), dec0),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    base_qs = tg_models.Shipment.objects.select_related("user").filter(
        status=tg_models.Shipment.Status.ISSUED,
        updated_at__date__gte=first_day,
        updated_at__date__lt=next_month,
    )
    if staff_filial is not None:
        base_qs = base_qs.filter(filial=staff_filial)

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
    if staff_filial is not None:
        day_ops_qs = day_ops_qs.filter(filial=staff_filial)
    day_ops = day_ops_qs.annotate(amount=amount_expr).order_by("-updated_at")[:500]

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
            "calendar_cells": calendar_cells,
            "day_ops": day_ops,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_shipments_import(request):
    denied = _require_manager_role(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

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

    def _find_user_by_client_code(raw_code: str) -> tg_models.User | None:
        code = (raw_code or "").strip()
        if not code:
            return None

        qs_base = tg_models.User.objects.all()
        if staff_filial is not None:
            qs_base = qs_base.filter(filial=staff_filial)

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

    if request.method == "POST":
        action = (request.POST.get("action") or "preview").strip()
        if action == "save":
            payload = request.session.get(preview_key) or {}
            rows = payload.get("rows") or []
            group_status = payload.get("group_status")
            sent_date_raw = (payload.get("sent_date") or "").strip()
            sent_date = None
            if sent_date_raw:
                try:
                    sent_date = timezone.datetime.fromisoformat(sent_date_raw).date()
                except Exception:
                    sent_date = None
            price_per_kg = payload.get("price_per_kg")

            if not rows:
                report = {"error": "Сначала нажмите 'Проверить'."}
                form = ShipmentImportForm(initial={"sent_date": sent_date, "group_status": tg_models.ShipmentGroup.Status.ON_THE_WAY})
            else:
                created = 0
                skipped = 0
                errors: list[dict] = []

                with transaction.atomic():
                    group_obj = tg_models.ShipmentGroup.objects.create(
                        name=_next_group_name(),
                        status=group_status or tg_models.ShipmentGroup.Status.ON_THE_WAY,
                        sent_date=sent_date,
                        filial=staff_filial,
                    )

                    for r in rows:
                        tracking = (r.get("tracking") or "").strip()
                        client_code = (r.get("client_code") or "").strip()
                        import_status = r.get("import_status") or tg_models.Shipment.ImportStatus.OK
                        user_id = r.get("user_id")

                        if not tracking:
                            skipped += 1
                            continue

                        user_obj = None
                        if user_id:
                            user_obj = tg_models.User.objects.filter(id=user_id).first()

                        if user_obj is not None and staff_filial is not None and user_obj.filial_id != staff_filial.id:
                            user_obj = None
                            import_status = tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND

                        if user_obj is not None:
                            exists_qs = tg_models.Shipment.objects.filter(user=user_obj, tracking_number=tracking)
                            if staff_filial is not None:
                                exists_qs = exists_qs.filter(filial=staff_filial)
                            exists = exists_qs.exists()
                            if exists:
                                skipped += 1
                                continue

                        sh = tg_models.Shipment(
                            filial=staff_filial,
                            user=user_obj,
                            group=group_obj,
                            tracking_number=tracking,
                            status=group_obj.status or tg_models.Shipment.Status.ON_THE_WAY,
                            client_code_raw=client_code,
                            import_status=import_status,
                        )
                        if price_per_kg is not None and price_per_kg != "":
                            try:
                                sh.price_per_kg = price_per_kg
                            except Exception:
                                pass
                        sh.save()
                        created += 1

                        if user_obj is not None and import_status == tg_models.Shipment.ImportStatus.OK:
                            _notify_user_arrival(user_obj=user_obj, tracking=tracking, shipment_status=sh.status)

                request.session.pop(preview_key, None)
                return redirect("manager_group_detail", group_id=group_obj.id)
        else:
            form = ShipmentImportForm(request.POST, request.FILES)
            if form.is_valid():
                sent_date = form.cleaned_data.get("sent_date")
                group_status = form.cleaned_data.get("group_status")
                price_per_kg = form.cleaned_data.get("price_per_kg")
                f = form.cleaned_data.get("file")

                rows: list[dict] = []
                errors: list[dict] = []
                try:
                    wb = load_workbook(filename=f, read_only=True, data_only=True)
                    ws = wb.active
                    for idx, row in enumerate(ws.iter_rows(min_row=1), start=1):
                        tracking = str(row[0].value or "").strip() if len(row) > 0 else ""
                        client_code = str(row[1].value or "").strip() if len(row) > 1 else ""
                        if not tracking and not client_code:
                            continue

                        if tracking and not _looks_like_tracking(tracking):
                            continue

                        if not client_code:
                            rows.append({
                                "row": idx,
                                "tracking": tracking,
                                "client_code": "",
                                "user_id": None,
                                "user_name": "",
                                "import_status": tg_models.Shipment.ImportStatus.NO_CLIENT_CODE,
                            })
                            continue

                        user_obj = _find_user_by_client_code(client_code)
                        if not user_obj:
                            rows.append({
                                "row": idx,
                                "tracking": tracking,
                                "client_code": client_code,
                                "user_id": None,
                                "user_name": "",
                                "import_status": tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND,
                            })
                            continue

                        rows.append({
                            "row": idx,
                            "tracking": tracking,
                            "client_code": client_code,
                            "user_id": user_obj.id,
                            "user_name": getattr(user_obj, "full_name", "") or getattr(user_obj, "client_code", ""),
                            "import_status": tg_models.Shipment.ImportStatus.OK,
                        })
                except Exception as e:
                    report = {"error": str(e)}
                else:
                    request.session[preview_key] = {
                        "sent_date": sent_date.isoformat() if sent_date else "",
                        "group_status": group_status,
                        "price_per_kg": str(price_per_kg) if price_per_kg is not None else "",
                        "rows": rows,
                    }
                    preview_rows = rows
                    preview_summary = {
                        "total": len(rows),
                        "ok": sum(1 for r in rows if (r.get("import_status") == tg_models.Shipment.ImportStatus.OK)),
                        "no_client_code": sum(1 for r in rows if (r.get("import_status") == tg_models.Shipment.ImportStatus.NO_CLIENT_CODE)),
                        "client_not_found": sum(1 for r in rows if (r.get("import_status") == tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND)),
                    }
                    report = {"errors": errors}
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
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_shipment_new(request):
    denied = _require_manager_role(request)
    if denied is not None:
        return denied

    staff_filial, denied_filial = _get_staff_filial_or_denied(request)
    if denied_filial is not None:
        return denied_filial

    if request.method == "POST":
        form = ShipmentCreateForm(request.POST, staff_filial=staff_filial)
        if form.is_valid():
            shipment = form.save(staff_filial=staff_filial)
            return redirect("manager_shipment_detail", shipment_id=shipment.id)
    else:
        form = ShipmentCreateForm(staff_filial=staff_filial)

    return render(request, "contacts/manager/shipment_new.html", {"nav": "shipments", "form": form, **_role_ctx(request)})


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
