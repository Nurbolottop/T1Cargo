from django.contrib.auth.models import User as AuthUser
from django.db import models
from django.db.models import Q

from apps.base import models as base_models

class User(models.Model):
    class ClientType(models.TextChoices):
        INDIVIDUAL = "individual", "Физ. лицо"
        BUSINESS = "business", "Бизнес"

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        CLIENT_REGISTERED = "client_registered", "Клиент (Зарегистрирован)"

    class ClientStatus(models.TextChoices):
        NEW = "new", "Новый"
        OLD = "old", "Старый"

    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True, verbose_name="Telegram ID")
    username = models.CharField(max_length=255, blank=True, default="", verbose_name="Username")
    first_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Имя")
    last_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Фамилия")
    language_code = models.CharField(max_length=32, blank=True, default="", verbose_name="Код языка")

    full_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Полное имя")
    phone = models.CharField(max_length=64, blank=True, default="", verbose_name="Телефон")
    address = models.CharField(max_length=512, blank=True, default="", verbose_name="Адрес")

    filial = models.ForeignKey(
        base_models.Filial,
        on_delete=models.SET_NULL,
        related_name="clients",
        blank=True,
        null=True,
        verbose_name="Филиал",
    )

    client_code = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Код клиента",
    )
    client_type = models.CharField(
        max_length=16,
        choices=ClientType.choices,
        default=ClientType.INDIVIDUAL,
        blank=True,
        null=True,
        verbose_name="Тип клиента",
    )
    total_debt = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name="Общий долг",
    )

    storage_penalty_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        blank=True,
        verbose_name="Штраф за хранение (итого)",
    )
    storage_penalty_last_charged_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="Дата последнего начисления штрафа",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name="Статус",
    )

    client_status = models.CharField(
        max_length=16,
        choices=ClientStatus.choices,
        default=ClientStatus.NEW,
        verbose_name="Статус клиента",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.client_code:
            return self.client_code
        if self.telegram_id is not None:
            return str(self.telegram_id)
        return str(self.id)


class ShipmentGroup(models.Model):
    class Status(models.TextChoices):
        ON_THE_WAY = "on_the_way", "В пути"
        BISHKEK = "bishkek", "В Бишкеке"
        WAREHOUSE = "warehouse", "Готов к выдаче"
        ISSUED = "issued", "Выдано"

    filial = models.ForeignKey(
        base_models.Filial,
        on_delete=models.SET_NULL,
        related_name="shipment_groups",
        blank=True,
        null=True,
        verbose_name="Филиал",
    )
    name = models.CharField(max_length=64, unique=True, verbose_name="Название группы")
    sent_date = models.DateField(blank=True, null=True, verbose_name="Дата отправки")
    bishkek_marked = models.BooleanField(default=False, verbose_name="Отмечено: В Бишкеке")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ON_THE_WAY, verbose_name="Статус группы")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class Shipment(models.Model):
    class PricingMode(models.TextChoices):
        KG = "kg", "По кг"
        GABARIT = "gabarit", "По габариту"

    class Status(models.TextChoices):
        ON_THE_WAY = "on_the_way", "В пути"
        BISHKEK = "bishkek", "В Бишкеке"
        WAREHOUSE = "warehouse", "Готов к выдаче"
        ISSUED = "issued", "Выдано"

    class ImportStatus(models.TextChoices):
        OK = "ok", "Ок"
        NO_CLIENT_CODE = "no_client_code", "Неизвестный клиент"
        CLIENT_NOT_FOUND = "client_not_found", "Клиент не найден"

    filial = models.ForeignKey(
        base_models.Filial,
        on_delete=models.SET_NULL,
        related_name="shipments",
        blank=True,
        null=True,
        verbose_name="Филиал",
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="shipments", blank=True, null=True, verbose_name="Клиент")
    group = models.ForeignKey(ShipmentGroup, on_delete=models.SET_NULL, related_name="shipments", blank=True, null=True, verbose_name="Группа")
    client_code_raw = models.CharField(max_length=32, blank=True, default="", verbose_name="Код клиента (из импорта)")
    tracking_number = models.CharField(max_length=128, verbose_name="Трек-номер")
    weight_kg = models.DecimalField(max_digits=10, decimal_places=3, default=0, blank=True, verbose_name="Вес (кг)")
    price_per_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, verbose_name="Цена за кг")
    total_price = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True, verbose_name="Итоговая стоимость")

    pricing_mode = models.CharField(
        max_length=16,
        choices=PricingMode.choices,
        default=PricingMode.KG,
        verbose_name="Способ расчёта",
    )

    storage_penalty_total = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True, verbose_name="Штраф за хранение (итого)")
    storage_penalty_last_charged_date = models.DateField(blank=True, null=True, verbose_name="Дата последнего начисления штрафа")

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ON_THE_WAY, verbose_name="Статус")
    import_status = models.CharField(max_length=32, choices=ImportStatus.choices, default=ImportStatus.OK, verbose_name="Статус импорта")
    arrival_date = models.DateField(blank=True, null=True, verbose_name="Дата прибытия")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Посылка"
        verbose_name_plural = "Посылки"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.tracking_number


def attach_orphan_shipments_to_user(user_obj: "User") -> int:
    user_id = getattr(user_obj, "id", None)
    client_code = (getattr(user_obj, "client_code", "") or "").strip()
    filial_id = getattr(getattr(user_obj, "filial", None), "id", None)
    if not user_id or not client_code or not filial_id:
        return 0

    suffix = ""
    if "-" in client_code:
        try:
            suffix = client_code.split("-", 1)[1].strip()
        except Exception:
            suffix = ""

    qs = Shipment.objects.filter(
        user__isnull=True,
        import_status=Shipment.ImportStatus.CLIENT_NOT_FOUND,
        filial_id=filial_id,
    )

    code_match = Q(client_code_raw__iexact=client_code)
    if suffix:
        code_match = code_match | Q(client_code_raw__iexact=suffix)
    qs = qs.filter(code_match)

    updated = qs.update(user_id=user_id, import_status=Shipment.ImportStatus.OK)
    return int(updated or 0)


class UsersSH(AuthUser):
    class Role(models.TextChoices):
        MANAGER = "manager", "Менеджер"
        DIRECTOR = "director", "Директор"

    role = models.CharField(max_length=16, choices=Role.choices, verbose_name="Роль")
    filial = models.ForeignKey(
        base_models.Filial,
        on_delete=models.SET_NULL,
        related_name="staff",
        blank=True,
        null=True,
        verbose_name="Филиал",
    )

    class Meta:
        verbose_name = "Штатный"
        verbose_name_plural = "Штатные"
        ordering = ["role", "-date_joined"]

    def __str__(self) -> str:
        return f"{self.username}"