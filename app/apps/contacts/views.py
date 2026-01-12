from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from apps.telegram_bot import models as tg_models
from apps.base import models as base_models
from apps.telegram_bot.views import _send_telegram_message
from .forms import ShipmentCreateForm, ShipmentImportForm

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
    return {"is_director": _is_director(u), "is_manager": _is_manager(u)}


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

    counts = (
        tg_models.Shipment.objects.values("status")
        .annotate(c=Count("id"))
        .order_by("status")
    )
    status_map = {row["status"]: row["c"] for row in counts}
    total_shipments = sum(status_map.values())

    since = timezone.now() - timezone.timedelta(days=7)
    new_clients_7d = tg_models.User.objects.filter(created_at__gte=since).count()

    last_shipments = tg_models.Shipment.objects.select_related("user").order_by("-created_at")[:10]
    return render(
        request,
        "contacts/manager/dashboard.html",
        {
            "nav": "dashboard",
            "total_shipments": total_shipments,
            "status_counts": status_map,
            "new_clients_7d": new_clients_7d,
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
    qs = (
        tg_models.Shipment.objects.select_related("group")
        .filter(user__isnull=True, import_status=tg_models.Shipment.ImportStatus.NO_CLIENT_CODE)
        .order_by("-created_at")
    )
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
    qs = (
        tg_models.Shipment.objects.select_related("group")
        .filter(user__isnull=True, import_status=tg_models.Shipment.ImportStatus.CLIENT_NOT_FOUND)
        .order_by("-created_at")
    )
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

    q = (request.GET.get("q") or "").strip()
    qs = tg_models.User.objects.all().order_by("-created_at")
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

    client = get_object_or_404(tg_models.User, id=user_id)
    shipments = tg_models.Shipment.objects.filter(user=client).order_by("-created_at")[:200]
    return render(
        request,
        "contacts/manager/client_detail.html",
        {"nav": "clients", "client": client, "shipments": shipments, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
def manager_groups(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied
    groups = tg_models.ShipmentGroup.objects.all().order_by("-created_at")[:300]
    return render(request, "contacts/manager/groups.html", {"nav": "groups", "groups": groups, **_role_ctx(request)})


@login_required(login_url="/manager/login/")
def manager_group_detail(request, group_id: int):
    denied = _require_manager(request)
    if denied is not None:
        return denied
    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
    shipments = tg_models.Shipment.objects.select_related("user").filter(group=group).order_by("-created_at")
    return render(
        request,
        "contacts/manager/group_detail.html",
        {"nav": "groups", "group": group, "shipments": shipments, **_role_ctx(request)},
    )


@login_required(login_url="/manager/login/")
@csrf_protect
def manager_group_sorting(request, group_id: int):
    denied = _require_editor_role(request)
    if denied is not None:
        return denied

    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
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

    default_price_per_kg = None
    if shipment is not None and shipment.user and shipment.user.filial:
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
                filial_price = None
                if shipment.user and shipment.user.filial:
                    filial_price = shipment.user.filial.default_price_per_kg
                if filial_price is None:
                    error = "Не задана цена за кг в филиале клиента (default_price_per_kg)."
                else:
                    with transaction.atomic():
                        shipment.weight_kg = weight
                        shipment.price_per_kg = filial_price
                        shipment.total_price = (weight * filial_price).quantize(Decimal("0.01"))
                        shipment.status = tg_models.Shipment.Status.WAREHOUSE
                        shipment.arrival_date = timezone.now().date()
                        shipment.save(update_fields=["weight_kg", "price_per_kg", "total_price", "status", "arrival_date", "updated_at"])

                        if group.status != tg_models.ShipmentGroup.Status.WAREHOUSE:
                            group.status = tg_models.ShipmentGroup.Status.WAREHOUSE
                            group.save(update_fields=["status", "updated_at"])

                    if shipment.user and getattr(shipment.user, "telegram_id", None):
                        token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
                        if token:
                            currency = "KGS"
                            try:
                                currency = (shipment.user.filial.currency or "KGS") if shipment.user.filial else "KGS"
                            except Exception:
                                currency = "KGS"
                            text = (
                                f"Ваш товар прибыл на склад.\n"
                                f"Трек: {shipment.tracking_number}\n"
                                f"Вес: {shipment.weight_kg} кг\n"
                                f"Стоимость доставки: {shipment.total_price} {currency}\n\n"
                                f"Бесплатное хранение 3 дня, затем будет начисляться штраф."
                            )
                            try:
                                _send_telegram_message(token=token, chat_id=int(shipment.user.telegram_id), text=text)
                            except Exception:
                                pass

                    return redirect("manager_group_sorting", group_id=group.id)

        default_price_per_kg = None
        if shipment is not None and shipment.user and shipment.user.filial:
            default_price_per_kg = shipment.user.filial.default_price_per_kg

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

    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
    group.status = tg_models.ShipmentGroup.Status.BISHKEK
    group.save(update_fields=["status", "updated_at"])

    token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
    if token:
        qs = tg_models.Shipment.objects.select_related("user").filter(group=group, user__isnull=False)
        for sh in qs:
            user_obj = sh.user
            chat_id = getattr(user_obj, "telegram_id", None)
            if not chat_id:
                continue
            try:
                _send_telegram_message(
                    token=token,
                    chat_id=int(chat_id),
                    text=f"Ваш товар прибыл в Бишкек.\nТрек: {sh.tracking_number}",
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

    group = get_object_or_404(tg_models.ShipmentGroup, id=group_id)
    shipment = get_object_or_404(tg_models.Shipment.objects.select_related("user"), id=shipment_id, group=group)

    if shipment.status != tg_models.Shipment.Status.ISSUED:
        shipment.status = tg_models.Shipment.Status.ISSUED
        shipment.save(update_fields=["status", "updated_at"])

        if shipment.user and getattr(shipment.user, "telegram_id", None):
            token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()
            if token:
                text = f"Ваш товар выдан.\nТрек: {shipment.tracking_number}"
                try:
                    _send_telegram_message(token=token, chat_id=int(shipment.user.telegram_id), text=text)
                except Exception:
                    pass

    all_issued = not tg_models.Shipment.objects.filter(group=group).exclude(status=tg_models.Shipment.Status.ISSUED).exists()
    if all_issued and group.status != tg_models.ShipmentGroup.Status.ISSUED:
        group.status = tg_models.ShipmentGroup.Status.ISSUED
        group.save(update_fields=["status", "updated_at"])

    return redirect("manager_group_detail", group_id=group.id)


@login_required(login_url="/manager/login/")
def manager_shipments(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = tg_models.Shipment.objects.select_related("user").all().order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(tracking_number__icontains=q)
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
            "statuses": tg_models.Shipment.Status.choices,
            **_role_ctx(request),
        },
    )


@login_required(login_url="/manager/login/")
def manager_shipments_import(request):
    denied = _require_manager_role(request)
    if denied is not None:
        return denied

    if load_workbook is None:
        return render(
            request,
            "contacts/manager/shipments_import.html",
            {
                "nav": "shipments",
                "form": ShipmentImportForm(),
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
            text = f"Ваш товар прибыл на склад.\nТрек: {tracking}"
        else:
            text = f"Ваш товар в пути.\nТрек: {tracking}"
        try:
            _send_telegram_message(token=token, chat_id=int(chat_id), text=text)
        except Exception:
            return

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
            shipment_status = payload.get("shipment_status")
            price_per_kg = payload.get("price_per_kg")

            if not rows:
                report = {"error": "Сначала нажмите 'Проверить'."}
                form = ShipmentImportForm()
            else:
                created = 0
                skipped = 0
                errors: list[dict] = []

                with transaction.atomic():
                    group_obj = tg_models.ShipmentGroup.objects.create(
                        name=_next_group_name(),
                        status=group_status or tg_models.ShipmentGroup.Status.ON_THE_WAY,
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

                        if user_obj is not None:
                            exists = tg_models.Shipment.objects.filter(user=user_obj, tracking_number=tracking).exists()
                            if exists:
                                skipped += 1
                                continue

                        sh = tg_models.Shipment(
                            user=user_obj,
                            group=group_obj,
                            tracking_number=tracking,
                            status=shipment_status or tg_models.Shipment.Status.ON_THE_WAY,
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
                report = {"created": created, "skipped": skipped, "errors": errors, "group_name": group_obj.name}
                form = ShipmentImportForm(initial={"group_status": group_status, "shipment_status": shipment_status, "price_per_kg": price_per_kg})
        else:
            form = ShipmentImportForm(request.POST, request.FILES)
            if form.is_valid():
                group_status = form.cleaned_data.get("group_status")
                shipment_status = form.cleaned_data.get("shipment_status")
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

                        user_obj = tg_models.User.objects.filter(client_code=client_code).first()
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
                        "group_status": group_status,
                        "shipment_status": shipment_status,
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
        form = ShipmentImportForm()

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

    if request.method == "POST":
        form = ShipmentCreateForm(request.POST)
        if form.is_valid():
            shipment = form.save()
            return redirect("manager_shipment_detail", shipment_id=shipment.id)
    else:
        form = ShipmentCreateForm()

    return render(request, "contacts/manager/shipment_new.html", {"nav": "shipments", "form": form, **_role_ctx(request)})


@login_required(login_url="/manager/login/")
def manager_shipment_detail(request, shipment_id: int):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    shipment = get_object_or_404(tg_models.Shipment.objects.select_related("user"), id=shipment_id)

    if request.method == "POST":
        denied_write = _require_editor_role(request)
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
