from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User as AuthUser
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

@admin.register(tg_models.User)
class UserAdmin(admin.ModelAdmin):
    inlines = (ShipmentInline,)
    list_display = (
        "client_code",
        "telegram_id",
        "username",
        "client_type",
        "filial",
        "status",
        "client_status",
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
    list_filter = ("status", "client_status", "client_type", "created_at")
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
                    "client_status",
                    "total_debt",
                    "filial",
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
    inlines = ()
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

@admin.register(tg_models.UsersSH)
class UsersSHAdmin(DjangoUserAdmin):
    model = tg_models.UsersSH
    list_display = ("username", "first_name", "last_name", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email")

    fieldsets = DjangoUserAdmin.fieldsets + (("Роль", {"fields": ("role", "filial")}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (("Роль", {"fields": ("role", "filial")}),)


def _ensure_userssh(user: AuthUser, role: str):
    if not user:
        return
    if hasattr(user, "userssh"):
        prof = user.userssh
        prof.role = role
        prof.save(update_fields=["role"])
        return
    tg_models.UsersSH.objects.create(user_ptr=user, role=role)


@admin.action(description="Сделать штатным: Менеджер")
def make_userssh_manager(modeladmin, request, queryset):
    for u in queryset:
        _ensure_userssh(u, tg_models.UsersSH.Role.MANAGER)


@admin.action(description="Сделать штатным: Директор")
def make_userssh_director(modeladmin, request, queryset):
    for u in queryset:
        _ensure_userssh(u, tg_models.UsersSH.Role.DIRECTOR)


try:
    admin.site.unregister(AuthUser)
except Exception:
    pass


@admin.register(AuthUser)
class AuthUserAdmin(DjangoUserAdmin):
    actions = [make_userssh_manager, make_userssh_director]



@admin.register(tg_models.ShipmentGroup)
class ShipmentGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "sent_date", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name",)
    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "name",
                    "sent_date",
                    "bishkek_marked",
                    "status",
                    "filial",
                )
            },
        ),
        (
            "Служебное",
            {"fields": ("created_at", "updated_at")},
        ),
    )

