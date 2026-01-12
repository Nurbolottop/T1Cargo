from django.contrib.auth.models import User as AuthUser
from django.db import models
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
        WAREHOUSE = "warehouse", "На складе"
        ISSUED = "issued", "Выдано"

    name = models.CharField(max_length=64, unique=True, verbose_name="Название группы")
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
    class Status(models.TextChoices):
        CREATED = "created", "Создан"
        IN_CHINA = "in_china", "В Китае"
        ON_THE_WAY = "on_the_way", "В пути"
        BISHKEK = "bishkek", "В Бишкеке"
        WAREHOUSE = "warehouse", "На складе"
        ISSUED = "issued", "Выдано"
        ARRIVED = "arrived", "Прибыл"
        DELIVERED = "delivered", "Доставлен"
        NOT_PICKED = "not_picked", "Не забрали"

    class ImportStatus(models.TextChoices):
        OK = "ok", "Ок"
        NO_CLIENT_CODE = "no_client_code", "Неизвестный клиент"
        CLIENT_NOT_FOUND = "client_not_found", "Клиент не найден"

    user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="shipments", blank=True, null=True, verbose_name="Клиент")
    group = models.ForeignKey(ShipmentGroup, on_delete=models.SET_NULL, related_name="shipments", blank=True, null=True, verbose_name="Группа")
    client_code_raw = models.CharField(max_length=32, blank=True, default="", verbose_name="Код клиента (из импорта)")
    tracking_number = models.CharField(max_length=128, verbose_name="Трек-номер")
    weight_kg = models.DecimalField(max_digits=10, decimal_places=3, default=0, blank=True, verbose_name="Вес (кг)")
    price_per_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, verbose_name="Цена за кг")
    total_price = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True, verbose_name="Итоговая стоимость")

    storage_penalty_total = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True, verbose_name="Штраф за хранение (итого)")
    storage_penalty_last_charged_date = models.DateField(blank=True, null=True, verbose_name="Дата последнего начисления штрафа")

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.CREATED, verbose_name="Статус")
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


class UsersSH(AuthUser):
    class Role(models.TextChoices):
        MANAGER = "manager", "Менеджер"
        DIRECTOR = "director", "Директор"

    role = models.CharField(max_length=16, choices=Role.choices, verbose_name="Роль")

    class Meta:
        verbose_name = "Штатный"
        verbose_name_plural = "Штатные"
        ordering = ["role", "-date_joined"]

    def __str__(self) -> str:
        return f"{self.username}"