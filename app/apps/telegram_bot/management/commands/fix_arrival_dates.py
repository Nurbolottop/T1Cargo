#!/usr/bin/env python3
"""
Исправить arrival_date для посылок созданных вчера без arrival_date.
Устанавливает arrival_date = дата создания посылки.

Использование:
    python manage.py fix_arrival_dates --date 2025-03-08
    python manage.py fix_arrival_dates --all  # для всех посылок без arrival_date
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.telegram_bot import models as tg_models


class Command(BaseCommand):
    help = "Исправить arrival_date для посылок без даты прибытия"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Дата создания в формате YYYY-MM-DD",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Обработать все посылки без arrival_date",
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

        # Build query: посылки без arrival_date
        qs = tg_models.Shipment.objects.filter(arrival_date__isnull=True)
        
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
            self.stdout.write(f"Обработка посылок за {target_date} без arrival_date")
        else:
            self.stdout.write("Обработка ВСЕХ посылок без arrival_date")

        count = qs.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Нет посылок без arrival_date"))
            return

        self.stdout.write(f"Найдено посылок для обработки: {count}")

        updated = 0
        errors = 0

        with transaction.atomic() if not dry_run else transaction.atomic(durable=False):
            for shipment in qs.iterator():
                try:
                    arrival_date = shipment.created_at.date()
                    
                    if dry_run:
                        self.stdout.write(
                            f"[DRY-RUN] {shipment.tracking_number} (ID: {shipment.id}): "
                            f"arrival_date = {arrival_date}"
                        )
                    else:
                        shipment.arrival_date = arrival_date
                        shipment.save(update_fields=["arrival_date", "updated_at"])
                        self.stdout.write(
                            f"Обновлено {shipment.tracking_number}: "
                            f"arrival_date = {arrival_date}"
                        )
                    
                    updated += 1
                    
                except Exception as e:
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
