from django.contrib import admin
from apps.telegram_bot import models as tg_models

class ShipmentInline(admin.TabularInline):
    model = tg_models.Shipment
    extra = 0
    fields = (
        "tracking_number",
        "status",
        "weight_kg",
        "price_per_kg",
        "total_price",
        "arrival_date",
        "created_at",
    )
    readonly_fields = ("created_at",)
    show_change_link = True

class PaymentInline(admin.TabularInline):
    model = tg_models.Payment
    extra = 0
    fields = ("shipment", "amount", "method", "paid_at", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("shipment",)
    show_change_link = True

class NotificationInline(admin.TabularInline):
    model = tg_models.Notification
    extra = 0
    fields = ("text", "is_read", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True

class StoragePenaltyInline(admin.StackedInline):
    model = tg_models.StoragePenalty
    extra = 0
    fields = (
        "free_days",
        "penalty_per_day",
        "days_overdue",
        "total_penalty",
        "calculated_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")
    show_change_link = True

@admin.register(tg_models.User)
class UserAdmin(admin.ModelAdmin):
    inlines = (ShipmentInline, PaymentInline, NotificationInline)
    list_display = (
        "client_code",
        "telegram_id",
        "username",
        "client_type",
        "status",
        "full_name",
        "phone",
        "total_debt",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "client_code",
        "telegram_id",
        "username",
        "first_name",
        "last_name",
        "full_name",
        "phone",
    )
    list_filter = ("status", "client_type", "created_at")
    list_select_related = False
    list_per_page = 50
    autocomplete_fields = ()
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "telegram_id",
                    "client_code",
                    "client_type",
                    "status",
                    "total_debt",
                )
            },
        ),
        (
            "Профиль Telegram",
            {
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "language_code",
                )
            },
        ),
        (
            "Контакты",
            {"fields": ("full_name", "phone", "address")},
        ),
        (
            "Служебное",
            {"fields": ("created_at", "updated_at")},
        ),
    )

@admin.register(tg_models.Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    inlines = (StoragePenaltyInline, PaymentInline)
    list_display = (
        "tracking_number",
        "user",
        "status",
        "weight_kg",
        "price_per_kg",
        "total_price",
        "arrival_date",
        "created_at",
    )
    list_filter = ("status", "arrival_date", "created_at")
    search_fields = ("tracking_number", "user__client_code", "user__telegram_id", "user__full_name")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "user",
                    "tracking_number",
                    "status",
                )
            },
        ),
        (
            "Стоимость",
            {"fields": ("weight_kg", "price_per_kg", "total_price")},
        ),
        (
            "Даты",
            {"fields": ("arrival_date", "created_at", "updated_at")},
        ),
    )

@admin.register(tg_models.Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("paid_at", "user", "shipment", "amount", "method", "created_at")
    list_filter = ("method", "paid_at", "created_at")
    search_fields = (
        "user__client_code",
        "user__telegram_id",
        "shipment__tracking_number",
    )
    autocomplete_fields = ("user", "shipment")
    readonly_fields = ("created_at", "updated_at")

@admin.register(tg_models.StoragePenalty)
class StoragePenaltyAdmin(admin.ModelAdmin):
    list_display = (
        "shipment",
        "free_days",
        "penalty_per_day",
        "days_overdue",
        "total_penalty",
        "calculated_at",
    )
    list_filter = ("calculated_at",)
    search_fields = ("shipment__tracking_number", "shipment__user__client_code")
    autocomplete_fields = ("shipment",)
    readonly_fields = ("created_at", "updated_at")

@admin.register(tg_models.Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

@admin.register(tg_models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("user__client_code", "user__telegram_id", "text")
    autocomplete_fields = ("user",)
