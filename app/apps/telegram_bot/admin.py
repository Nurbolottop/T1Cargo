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
    actions = ("attach_orphan_shipments",)
    list_display = (
        "tracking_number",
        "user",
        "client_code_raw",
        "import_status",
        "filial",
        "group",
        "status",
        "weight_kg",
        "price_per_kg",
        "total_price",
        "arrival_date",
        "issued_at",
        "created_at",
    )
    list_filter = ("status", "import_status", "filial", "group", "arrival_date", "created_at")
    search_fields = (
        "tracking_number",
        "client_code_raw",
        "user__client_code",
        "user__telegram_id",
        "user__full_name",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

    def get_fields(self, request, obj=None):
        fields = [
            f.name
            for f in self.model._meta.fields
            if getattr(f, "editable", False) and not getattr(f, "primary_key", False)
        ]
        fields.extend([f.name for f in self.model._meta.many_to_many if getattr(f, "editable", False)])
        for ro in self.get_readonly_fields(request, obj):
            if ro not in fields:
                fields.append(ro)
        return fields

    @admin.action(description="Привязать выбранные посылки к клиентам по коду")
    def attach_orphan_shipments(self, request, queryset):
        updated = 0
        skipped = 0

        for sh in queryset.select_related("filial").filter(user__isnull=True):
            raw = (getattr(sh, "client_code_raw", "") or "").strip()
            if not raw:
                skipped += 1
                continue

            cleaned = raw.replace(" ", "")
            if cleaned.endswith(".0") and cleaned[:-2].isdigit():
                cleaned = cleaned[:-2]

            filial = getattr(sh, "filial", None)
            prefix = (getattr(filial, "client_code_prefix", "") or "").strip().upper() if filial else ""

            if "-" in cleaned:
                code_norm = cleaned.upper()
            else:
                code_norm = f"{prefix}-{cleaned}" if prefix else cleaned

            users_qs = tg_models.User.objects.all()
            if filial is not None:
                users_qs = users_qs.filter(filial=filial)

            user_obj = users_qs.filter(client_code__iexact=code_norm).first()
            if user_obj is None and "-" not in code_norm:
                suffix = f"-{code_norm}"
                qs = users_qs.filter(client_code__iendswith=suffix)
                if qs.count() == 1:
                    user_obj = qs.first()

            if user_obj is None:
                skipped += 1
                continue

            sh.user = user_obj
            sh.import_status = tg_models.Shipment.ImportStatus.OK
            sh.save(update_fields=["user", "import_status"])
            updated += 1

        self.message_user(request, f"Готово. Привязано: {updated}. Пропущено: {skipped}.")

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



class ShipmentGroupInline(admin.TabularInline):
    model = tg_models.Shipment
    extra = 0
    fields = (
        "tracking_number",
        "user",
        "status",
        "weight_kg",
        "total_price",
        "created_at",
    )
    readonly_fields = ("created_at",)
    show_change_link = True
    can_delete = True


@admin.register(tg_models.ShipmentGroup)
class ShipmentGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "sent_date", "filial", "price_per_kg", "created_at", "shipment_count")
    list_filter = ("status", "filial", "created_at")
    search_fields = ("name",)
    inlines = (ShipmentGroupInline,)
    actions = ("delete_selected_with_shipments",)
    
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
                    "price_per_kg",
                )
            },
        ),
        (
            "Служебное",
            {"fields": ("created_at", "updated_at")},
        ),
    )
    readonly_fields = ("created_at", "updated_at")
    
    def shipment_count(self, obj):
        return obj.shipments.count()
    shipment_count.short_description = "Кол-во посылок"
    
    def delete_model(self, request, obj):
        # Delete all shipments in this group first
        shipment_count = obj.shipments.count()
        obj.shipments.all().delete()
        # Then delete the group
        super().delete_model(request, obj)
        self.message_user(request, f"Группа удалена. Вместе с ней удалено {shipment_count} посылок.")
    
    @admin.action(description="Удалить выбранные группы с посылками")
    def delete_selected_with_shipments(self, request, queryset):
        total_groups = queryset.count()
        total_shipments = 0
        for group in queryset:
            total_shipments += group.shipments.count()
            group.shipments.all().delete()
        queryset.delete()
        self.message_user(request, f"Удалено {total_groups} групп и {total_shipments} посылок.")
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        # Remove default delete_selected action to avoid confusion
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

