import os
import time

from django.core.management.base import BaseCommand
from django.db.utils import OperationalError, ProgrammingError
from django.utils.autoreload import run_with_reloader
from apps.base.models import Settings
from apps.telegram_bot.bot_main_aiogram import start_bot


class Command(BaseCommand):
    help = "Run Telegram bot"
 
    def handle(self, *args, **options):
        retry_seconds = 10

        def _loop() -> None:
            while True:
                try:
                    settings_obj = Settings.objects.first()
                except (OperationalError, ProgrammingError) as exc:
                    self.stderr.write(self.style.ERROR(f"Database is not ready: {exc}"))
                    time.sleep(retry_seconds)
                    continue

                if not settings_obj:
                    self.stderr.write(self.style.ERROR("Settings not configured. Create Settings record in admin."))
                    time.sleep(retry_seconds)
                    continue

                if not settings_obj.is_bot_enabled:
                    self.stdout.write(self.style.WARNING("Bot is disabled in Settings"))
                    time.sleep(retry_seconds)
                    continue

                token = (settings_obj.telegram_token or "").strip()
                if not token:
                    self.stderr.write(self.style.ERROR("Telegram token is empty in Settings"))
                    time.sleep(retry_seconds)
                    continue

                self.stdout.write(self.style.SUCCESS("Bot started..."))
                start_bot(token)

                time.sleep(5)

        use_reloader = (os.environ.get("BOT_AUTORELOAD") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
        if use_reloader:
            run_with_reloader(_loop)
        else:
            _loop()
