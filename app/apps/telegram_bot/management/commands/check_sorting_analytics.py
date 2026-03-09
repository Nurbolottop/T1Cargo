#!/usr/bin/env python3
"""
Проверить аналитику сортировки на конкретную дату.

Использование:
    python manage.py check_sorting_analytics --date 2025-03-02
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, F, Count, Sum, DateField
from django.db.models.functions import Coalesce, TruncDate
from decimal import Decimal

from apps.telegram_bot import models as tg_models


class Command(BaseCommand):
    help = "Проверить аналитику сортировки на конкретную дату"

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

        # 1. Посылки с total_price > 0 (текущая логика аналитики)
        sorted_shipments = tg_models.Shipment.objects.filter(
            total_price__gt=0,
        ).annotate(
            d=Coalesce(
                F("arrival_date"),
                TruncDate("created_at"),
                output_field=DateField(),
            )
        ).filter(d=target_date)

        count_sorted = sorted_shipments.count()
        total_sorted = sorted_shipments.aggregate(total=Sum("total_price"))["total"] or Decimal("0")

        self.stdout.write(f"\n[Сортировка - текущая логика]")
        self.stdout.write(f"  Посылок: {count_sorted}")
        self.stdout.write(f"  Сумма: {total_sorted}")

        # 2. ВСЕ посылки за этот день (с любой ценой)
        all_shipments = tg_models.Shipment.objects.annotate(
            d=Coalesce(
                F("arrival_date"),
                TruncDate("created_at"),
                output_field=DateField(),
            )
        ).filter(d=target_date)

        count_all = all_shipments.count()
        
        # Статистика по ценам
        with_price = all_shipments.filter(total_price__gt=0).count()
        with_zero = all_shipments.filter(total_price=0).count()
        with_null = all_shipments.filter(total_price__isnull=True).count()

        self.stdout.write(f"\n[ВСЕ посылки за {target_date}]")
        self.stdout.write(f"  Всего посылок: {count_all}")
        self.stdout.write(f"  С total_price > 0: {with_price}")
        self.stdout.write(f"  С total_price = 0: {with_zero}")
        self.stdout.write(f"  С total_price = NULL: {with_null}")

        # 3. Детали посылок с ценой
        if count_sorted > 0:
            self.stdout.write(f"\n[Детали посылок с ценой]:")
            self.stdout.write(f"{'ID':<6} {'Tracking':<20} {'total_price':<12} {'arrival_date':<12} {'created_at':<20}")
            self.stdout.write("-" * 72)
            for sh in sorted_shipments[:30]:
                self.stdout.write(
                    f"{sh.id:<6} {str(sh.tracking_number)[:19]:<20} {sh.total_price:<12} "
                    f"{str(sh.arrival_date):<12} {sh.created_at.strftime('%Y-%m-%d %H:%M'):<20}"
                )

        # 4. Посылки без цены (где цена 0 или NULL)
        no_price = all_shipments.filter(Q(total_price=0) | Q(total_price__isnull=True))
        no_price_count = no_price.count()
        
        if no_price_count > 0:
            self.stdout.write(f"\n[Посылки БЕЗ цены (нужно проверить!)]:")
            self.stdout.write(f"{'ID':<6} {'Tracking':<20} {'total_price':<12} {'weight_kg':<10} {'price_per_kg':<12}")
            self.stdout.write("-" * 62)
            for sh in no_price[:20]:
                self.stdout.write(
                    f"{sh.id:<6} {str(sh.tracking_number)[:19]:<20} {str(sh.total_price):<12} "
                    f"{sh.weight_kg:<10} {sh.price_per_kg:<12}"
                )
