#!/usr/bin/env python3
"""
Проверить какие посылки попадают в аналитику на конкретную дату.

Использование:
    python manage.py check_analytics_date --date 2025-03-09
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, F, Count, Sum, DateField
from django.db.models.functions import Coalesce, TruncDate

from apps.telegram_bot import models as tg_models


class Command(BaseCommand):
    help = "Проверить какие посылки попадают в аналитику на конкретную дату"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            required=True,
            help="Дата для проверки (YYYY-MM-DD)",
        )

    def handle(self, *args, **options):
        date_str = options.get("date")
        try:
            from datetime import datetime
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            self.stderr.write(self.style.ERROR(f"Неверный формат даты: {date_str}"))
            return

        self.stdout.write(f"\n=== Проверка аналитики за {target_date} ===\n")

        # Получаем посылки с total_price > 0
        shipments = tg_models.Shipment.objects.filter(
            total_price__gt=0,
        ).annotate(
            d=Coalesce(
                F("arrival_date"),
                TruncDate("created_at"),
                output_field=DateField(),
            )
        ).filter(d=target_date).order_by("id")

        count = shipments.count()
        self.stdout.write(f"Всего посылок за {target_date}: {count}")

        if count == 0:
            return

        # Показываем первые 20 посылок
        self.stdout.write(f"\nПервые 20 посылок:")
        self.stdout.write(f"{'ID':<6} {'Tracking':<20} {'arrival_date':<12} {'created_at':<20} {'total_price':<12}")
        self.stdout.write("-" * 70)
        
        for sh in shipments[:20]:
            arrival = sh.arrival_date or "NULL"
            self.stdout.write(
                f"{sh.id:<6} {str(sh.tracking_number)[:19]:<20} {str(arrival):<12} "
                f"{sh.created_at.strftime('%Y-%m-%d %H:%M'):<20} {sh.total_price:<12}"
            )

        # Сумма
        from decimal import Decimal
        total = shipments.aggregate(total=Sum("total_price"))["total"] or Decimal("0")
        self.stdout.write(f"\nОбщая сумма: {total} сом")
