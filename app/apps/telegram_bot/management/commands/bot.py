from django.core.management.base import BaseCommand
from django.db.utils import OperationalError, ProgrammingError
from django.utils.autoreload import run_with_reloader
from apps.base.models import Settings
from apps.telegram_bot.bot_main import start_bot


class Command(BaseCommand):
    help = "Run Telegram bot"

    def handle(self, *args, **options):
        try:
            settings_obj = Settings.objects.first()
        except (OperationalError, ProgrammingError) as exc:
            self.stderr.write(self.style.ERROR(f"Database is not ready: {exc}"))
            return

        if not settings_obj:
            self.stderr.write(self.style.ERROR("Settings not configured. Create Settings record in admin."))
            return

        if not settings_obj.is_bot_enabled:
            self.stdout.write(self.style.WARNING("Bot is disabled in Settings"))
            return

        token = settings_obj.telegram_token
        if not token:
            self.stderr.write(self.style.ERROR("Telegram token is empty in Settings"))
            return

        def _run() -> None:
            self.stdout.write(self.style.SUCCESS("Bot started..."))
            start_bot(token)

        run_with_reloader(_run)
