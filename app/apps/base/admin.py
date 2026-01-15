from django.contrib import admin
from django.utils.html import format_html
from apps.base import models as base_models

# Register your models here.
class AdminIdInline(admin.StackedInline):
    model = base_models.AdminId
    fk_name = "settings"
    extra = 0

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
                    "website",
                )
            },
        ),
        (
            "Telegram",
            {
                "classes": ("collapse",),
                "fields": (
                    "telegram_bot_username",
                    "telegram_token",
                    "is_bot_enabled",
                    "registration_webapp_url",
                    "prohibited_goods_text",
                )
            },
        ),
        (
            "Сайт",
            {
                "classes": ("collapse",),
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
                "classes": ("collapse",),
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

@admin.register(base_models.Filial)
class FilialAdmin(admin.ModelAdmin):
    list_display = (
        "city",
        "name",
        "is_active",
        "manager_contact",
        "currency",
        "client_code_prefix",
        "china_client_code_prefix",
        "storage_penalty_per_day",
        "created_at",
    )
    list_filter = ("city", "is_active", "created_at")
    search_fields = (
        "name",
        "city",
        "address",
        "manager_contact",
        "china_warehouse_name",
        "china_warehouse_phone",
        "china_warehouse_address",
        "wholesale_order_text",
        "wholesale_whatsapp_phone",
    )
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "city",
                    "name",
                    "is_active",
                    "currency",
                )
            },
        ),
        (
            "ПВЗ / Офис",
            {
                "fields": (
                    "address",
                    "manager_contact",
                    "pvz_location_url",
                    "work_hours",
                    "instagram_url",
                    "email",
                )
            },
        ),
        (
            "Склад в Китае",
            {
                "fields": (
                    "china_warehouse_name",
                    "china_warehouse_phone",
                    "china_warehouse_address",
                )
            },
        ),
        (
            "Код клиента",
            {
                "fields": (
                    "client_code_prefix",
                    "china_client_code_prefix",
                    "client_code_start_number",
                    "client_code_last_number",
                )
            },
        ),
        (
            "Штрафы",
            {
                "fields": (
                    "default_price_per_kg",
                    "storage_penalty_per_day",
                )
            },
        ),
        (
            "Оптовые товары",
            {
                "fields": (
                    "wholesale_order_text",
                    "wholesale_whatsapp_phone",
                )
            },
        ),
        (
            "Служебное",
            {
                "classes": ("collapse",),
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )