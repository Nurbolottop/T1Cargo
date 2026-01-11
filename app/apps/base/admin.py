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

@admin.register(base_models.Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "address", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "phone", "address")
    readonly_fields = ("created_at", "updated_at")

@admin.register(base_models.Filial)
class FilialAdmin(admin.ModelAdmin):
    list_display = (
        "city",
        "name",
        "is_active",
        "manager_contact",
        "currency",
        "client_code_prefix",
        "client_code_start_number",
        "client_code_last_number",
        "wholesale_order_text",
        "created_at",
    )
    list_filter = ("city", "is_active", "created_at")
    search_fields = ("name", "city", "address", "wholesale_order_text")
    readonly_fields = ("created_at", "updated_at")

@admin.register(base_models.Instruction)
class InstructionAdmin(admin.ModelAdmin):
    list_display = ("title", "has_photo", "has_video", "has_link", "has_file", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "text")
    readonly_fields = ("created_at", "updated_at", "photo_preview")
    fields = (
        "title",
        "text",
        "photo",
        "photo_preview",
        "video_url",
        "link_url",
        "file",
        "created_at",
        "updated_at",
    )

    def photo_preview(self, obj: base_models.Instruction):
        if not obj or not getattr(obj, "photo", None):
            return "—"
        return format_html('<img src="{}" style="max-height: 120px;" />', obj.photo.url)

    photo_preview.short_description = "Превью фото"

    def has_photo(self, obj: base_models.Instruction) -> bool:
        return bool(getattr(obj, "photo", None))

    has_photo.boolean = True
    has_photo.short_description = "Фото"

    def has_video(self, obj: base_models.Instruction) -> bool:
        return bool((getattr(obj, "video_url", "") or "").strip())

    has_video.boolean = True
    has_video.short_description = "Видео"

    def has_link(self, obj: base_models.Instruction) -> bool:
        return bool((getattr(obj, "link_url", "") or "").strip())

    has_link.boolean = True
    has_link.short_description = "Ссылка"

    def has_file(self, obj: base_models.Instruction) -> bool:
        return bool(getattr(obj, "file", None))

    has_file.boolean = True
    has_file.short_description = "Файл"