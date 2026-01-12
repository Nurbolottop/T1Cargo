from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.base import models as base_models
from apps.telegram_bot import models as tg_models
from apps.telegram_bot.views import _send_telegram_message


class Command(BaseCommand):
    help = "Charge daily storage penalties for shipments after free storage period"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="date",
            default="",
            help="Charge penalties up to this date (YYYY-MM-DD). Default: today",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Calculate and print charges but do not write to DB",
        )

    def handle(self, *args, **options):
        raw_date = (options.get("date") or "").strip()
        dry_run = bool(options.get("dry_run"))

        today = timezone.now().date()
        if raw_date:
            try:
                today = timezone.datetime.fromisoformat(raw_date).date()
            except Exception:
                self.stderr.write(self.style.ERROR("Invalid --date. Expected YYYY-MM-DD"))
                return

        free_days = 3

        token = (getattr(base_models.Settings.objects.first(), "telegram_token", "") or "").strip()

        qs = (
            tg_models.Shipment.objects.select_related("user", "user__filial")
            .filter(status=tg_models.Shipment.Status.WAREHOUSE)
            .exclude(user__isnull=True)
            .exclude(arrival_date__isnull=True)
        )

        total_shipments = 0
        charged_shipments = 0
        total_amount = Decimal("0")

        for sh in qs.iterator():
            total_shipments += 1

            user_obj = sh.user
            filial_obj = getattr(user_obj, "filial", None)
            if filial_obj is None:
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

            last = sh.storage_penalty_last_charged_date
            start_date = max(last or free_until, free_until)

            if start_date >= today:
                continue

            days_to_charge = (today - start_date).days
            if days_to_charge <= 0:
                continue

            amount = (Decimal(days_to_charge) * per_day).quantize(Decimal("0.01"))
            if amount <= 0:
                continue

            charged_shipments += 1
            total_amount += amount

            self.stdout.write(
                f"Shipment #{sh.id} {sh.tracking_number}: +{amount} ({days_to_charge} days * {per_day})"
            )

            if dry_run:
                continue

            with transaction.atomic():
                sh.storage_penalty_total = (Decimal(sh.storage_penalty_total or 0) + amount).quantize(Decimal("0.01"))
                sh.storage_penalty_last_charged_date = today
                sh.save(update_fields=["storage_penalty_total", "storage_penalty_last_charged_date", "updated_at"])

                user_obj.total_debt = (Decimal(user_obj.total_debt or 0) + amount).quantize(Decimal("0.01"))
                user_obj.save(update_fields=["total_debt", "updated_at"])

            if token and getattr(user_obj, "telegram_id", None):
                currency = "KGS"
                try:
                    currency = (filial_obj.currency or "KGS") if filial_obj else "KGS"
                except Exception:
                    currency = "KGS"

                text = (
                    "Начислен штраф за хранение.\n"
                    f"Трек: {sh.tracking_number}\n"
                    f"Штраф: {amount} {currency}\n"
                    f"Долг: {user_obj.total_debt} {currency}"
                )
                try:
                    _send_telegram_message(token=token, chat_id=int(user_obj.telegram_id), text=text)
                except Exception:
                    pass

        self.stdout.write(
            self.style.SUCCESS(
                f"Checked: {total_shipments}, charged: {charged_shipments}, total: {total_amount}"
            )
        )
