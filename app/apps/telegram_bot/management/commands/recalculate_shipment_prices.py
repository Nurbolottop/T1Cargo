#!/usr/bin/env python3
"""
Пересчитать total_price для посылок с весом и ценой за кг, но без итоговой цены.

Использование:
    python manage.py recalculate_shipment_prices --date 2025-03-08
    python manage.py recalculate_shipment_prices --all  # для всех посылок
"""
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.telegram_bot import models as tg_models


class Command(BaseCommand):
    help = "Пересчитать total_price для посылок с весом и ценой за кг"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Дата в формате YYYY-MM-DD (по умолчанию вчера)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Обработать все посылки, не только за конкретную дату",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать что будет сделано, но не сохранять",
        )

    def handle(self, *args, **options):
        date_str = options.get("date")
        all_shipments = options.get("all")
        dry_run = options.get("dry_run")

        # Build query
        qs = tg_models.Shipment.objects.filter(
            weight_kg__gt=0,
            price_per_kg__gt=0,
        ).filter(
            # total_price is null or 0
            # Using Q for OR condition: total_price__isnull=True OR total_price=0
        )
        
        # Filter by date if specified
        if not all_shipments:
            if date_str:
                try:
                    from datetime import datetime
                    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    self.stderr.write(self.style.ERROR(f"Неверный формат даты: {date_str}. Используйте YYYY-MM-DD"))
                    return
            else:
                # Default: yesterday
                target_date = timezone.localdate() - timezone.timedelta(days=1)
            
            qs = qs.filter(created_at__date=target_date)
            self.stdout.write(f"Обработка посылок за {target_date}")
        else:
            self.stdout.write("Обработка ВСЕХ посылок")

        # Filter: total_price is null or 0
        from django.db.models import Q
        qs = qs.filter(
            Q(total_price__isnull=True) | Q(total_price=0)
        )

        count = qs.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Нет посылок для обработки"))
            return

        self.stdout.write(f"Найдено посылок для обработки: {count}")

        updated = 0
        errors = 0

        with transaction.atomic() if not dry_run else transaction.atomic(durable=False):
            for shipment in qs.iterator():
                try:
                    weight = Decimal(str(shipment.weight_kg))
                    price = Decimal(str(shipment.price_per_kg))
                    
                    if weight <= 0 or price <= 0:
                        continue
                    
                    new_total = (weight * price).quantize(Decimal("0.01"))
                    
                    if dry_run:
                        self.stdout.write(
                            f"[DRY-RUN] {shipment.tracking_number}: "
                            f"{shipment.weight_kg} кг × {shipment.price_per_kg} = {new_total} сом"
                        )
                    else:
                        shipment.total_price = new_total
                        # Also set arrival_date if not set (use created_at date for proper analytics tracking)
                        update_fields = ["total_price", "updated_at"]
                        if not shipment.arrival_date:
                            shipment.arrival_date = shipment.created_at.date()
                            update_fields.append("arrival_date")
                        shipment.save(update_fields=update_fields)
                        self.stdout.write(
                            f"Обновлено {shipment.tracking_number}: "
                            f"{shipment.weight_kg} кг × {shipment.price_per_kg} = {new_total} сом"
                        )
                    
                    updated += 1
                    
                except (InvalidOperation, TypeError, ValueError) as e:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Ошибка обработки {shipment.tracking_number} (ID: {shipment.id}): {e}"
                        )
                    )
                    errors += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY-RUN] Было бы обновлено: {updated}, ошибок: {errors}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Обновлено: {updated}, ошибок: {errors}"))
