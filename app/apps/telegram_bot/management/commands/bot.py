import os

from django.core.management.base import BaseCommand
from django.utils.autoreload import run_with_reloader

from apps.telegram_bot.bot_main import start_bot


class Command(BaseCommand):
    help = "Run Telegram bot"

    def handle(self, *args, **options):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN not found in env"))
            return

        def _run() -> None:
            self.stdout.write(self.style.SUCCESS("Bot started..."))
            start_bot(token)

        run_with_reloader(_run)
