from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.telegram_bot import models as tg_models
from apps.base import models as base_models

from .forms import ShipmentCreateForm, ShipmentImportForm, PreClientCreateForm

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover
    load_workbook = None


def _manager_access_check(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return bool(getattr(user, "is_staff", False))


def manager_login(request):
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if _manager_access_check(request):
                return redirect("manager_dashboard")
            logout(request)
            return render(
                request,
                "contacts/manager/login.html",
                {"error": "Нет доступа"},
            )
        return render(
            request,
            "contacts/manager/login.html",
            {"error": "Неверный логин или пароль"},
        )

    if request.user.is_authenticated and _manager_access_check(request):
        return redirect("manager_dashboard")

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


@login_required(login_url="/manager/login/")
def manager_dashboard(request):
    denied = _require_manager(request)
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
        },
    )


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
        {"nav": "clients", "clients": clients, "q": q},
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
        {"nav": "clients", "client": client, "shipments": shipments},
    )


@login_required(login_url="/manager/login/")
def manager_client_new(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    error = None
    saved = (request.GET.get("saved") or "").strip() == "1"

    wh = base_models.Warehouse.objects.order_by("name").first()
    code_prefix = ((getattr(wh, "name", "") or "").strip().upper() + "-") if wh and (getattr(wh, "name", "") or "").strip() else ""
    if request.method == "POST":
        form = PreClientCreateForm(request.POST)
        if form.is_valid():
            full_client_code = f"{code_prefix}{form.cleaned_data['client_code']}" if code_prefix else form.cleaned_data["client_code"]
            if tg_models.User.objects.filter(client_code__iexact=full_client_code).exists():
                error = "Код уже используется"
                return render(
                    request,
                    "contacts/manager/client_new.html",
                    {"nav": "clients", "form": form, "error": error, "saved": False, "code_prefix": code_prefix},
                )

            filial_obj = (
                base_models.Filial.objects.filter(is_active=True, city__iexact="Ош").order_by("name").first()
                or base_models.Filial.objects.filter(is_active=True).order_by("city", "name").first()
            )
            if filial_obj is None:
                error = "Нет активных филиалов. Сначала создайте филиал." 
            else:
                tg_models.User.objects.create(
                    telegram_id=None,
                    client_code=full_client_code,
                    phone=form.cleaned_data["phone"],
                    filial=filial_obj,
                    status=tg_models.User.Status.NEW,
                    client_status=tg_models.User.ClientStatus.OLD,
                    client_type=tg_models.User.ClientType.INDIVIDUAL,
                )
                return redirect(reverse("manager_client_new") + "?saved=1")
    else:
        form = PreClientCreateForm()

    return render(
        request,
        "contacts/manager/client_new.html",
        {"nav": "clients", "form": form, "error": error, "saved": saved, "code_prefix": code_prefix},
    )


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
        },
    )


@login_required(login_url="/manager/login/")
def manager_shipments_import(request):
    denied = _require_manager(request)
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

    report = None
    if request.method == "POST":
        form = ShipmentImportForm(request.POST, request.FILES)
        if form.is_valid():
            status = form.cleaned_data.get("status")
            price_per_kg = form.cleaned_data.get("price_per_kg")
            f = form.cleaned_data.get("file")

            created = 0
            skipped = 0
            errors: list[dict] = []

            try:
                wb = load_workbook(filename=f, read_only=True, data_only=True)
                ws = wb.active

                for idx, row in enumerate(ws.iter_rows(min_row=1), start=1):
                    try:
                        tracking = str(row[0].value or "").strip() if len(row) > 0 else ""
                        client_code = str(row[1].value or "").strip() if len(row) > 1 else ""

                        if not tracking or not client_code:
                            skipped += 1
                            continue

                        user_obj = tg_models.User.objects.filter(client_code=client_code).first()
                        if not user_obj:
                            errors.append({"row": idx, "tracking": tracking, "client_code": client_code, "error": f"Клиент не найден: {client_code}"})
                            continue

                        exists = tg_models.Shipment.objects.filter(user=user_obj, tracking_number=tracking).exists()
                        if exists:
                            skipped += 1
                            continue

                        sh = tg_models.Shipment(
                            user=user_obj,
                            tracking_number=tracking,
                            status=status,
                        )
                        if price_per_kg is not None:
                            sh.price_per_kg = price_per_kg

                        sh.save()
                        created += 1
                    except Exception as e:
                        errors.append({
                            "row": idx,
                            "tracking": tracking if "tracking" in locals() else "",
                            "client_code": client_code if "client_code" in locals() else "",
                            "error": str(e),
                        })
            except Exception as e:
                report = {"error": str(e)}
            else:
                report = {"created": created, "skipped": skipped, "errors": errors}
        else:
            report = {"error": "Проверьте форму. Есть ошибки."}
    else:
        form = ShipmentImportForm()

    return render(
        request,
        "contacts/manager/shipments_import.html",
        {"nav": "shipments", "form": form, "report": report},
    )


@login_required(login_url="/manager/login/")
def manager_shipment_new(request):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    if request.method == "POST":
        form = ShipmentCreateForm(request.POST)
        if form.is_valid():
            shipment = form.save()
            return redirect("manager_shipment_detail", shipment_id=shipment.id)
    else:
        form = ShipmentCreateForm()

    return render(request, "contacts/manager/shipment_new.html", {"nav": "shipments", "form": form})


@login_required(login_url="/manager/login/")
def manager_shipment_detail(request, shipment_id: int):
    denied = _require_manager(request)
    if denied is not None:
        return denied

    shipment = get_object_or_404(tg_models.Shipment.objects.select_related("user"), id=shipment_id)

    if request.method == "POST":
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
        {"nav": "shipments", "shipment": shipment, "statuses": tg_models.Shipment.Status.choices},
    )
