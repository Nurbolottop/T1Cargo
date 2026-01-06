from django.contrib import admin
from django.utils.html import format_html
from apps.base import models as base_models

# Register your models here.

class AdminIdInline(admin.StackedInline):
    model = base_models.AdminId

@admin.register(base_models.Settings)
class SettingsAdmin(admin.ModelAdmin):
    inlines = (AdminIdInline,)
    fieldsets = (
        (
            "Компания",
            {
                "fields": (
                    "title",
                    "phone",
                    "email",
                    "website",
                    "manager_contact",
                )
            },
        ),
        (
            "Telegram",
            {
                "fields": (
                    "telegram_bot_username",
                    "telegram_token",
                    "is_bot_enabled",
                )
            },
        ),
        (
            "Финансы",
            {
                "fields": (
                    "currency",
                    "default_price_per_kg",
                )
            },
        ),
        (
            "Сайт",
            {
                "fields": (
                    "is_site_enabled",
                    "logo",
                    "icon",
                    "logo_preview",
                    "icon_preview",
                )
            },
        ),
        (
            "Служебное",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at", "logo_preview", "icon_preview")

    def has_add_permission(self, request):
        if base_models.Settings.objects.exists():
            return False
        return super().has_add_permission(request)

    def logo_preview(self, obj: base_models.Settings):
        if not obj or not getattr(obj, "logo", None):
            return "—"
        return format_html('<img src="{}" style="max-height: 80px;" />', obj.logo.url)

    logo_preview.short_description = "Превью логотипа"

    def icon_preview(self, obj: base_models.Settings):
        if not obj or not getattr(obj, "icon", None):
            return "—"
        return format_html('<img src="{}" style="max-height: 80px;" />', obj.icon.url)

    icon_preview.short_description = "Превью иконки"


