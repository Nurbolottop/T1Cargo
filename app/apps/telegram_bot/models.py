from django.contrib.auth.models import User as AuthUser
from django.db import models


class User(models.Model):
    class ClientType(models.TextChoices):
        INDIVIDUAL = "individual", "Физ. лицо"
        BUSINESS = "business", "Бизнес"

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        CLIENT_REGISTERED = "client_registered", "Клиент (Зарегистрирован)"

    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    username = models.CharField(max_length=255, blank=True, default="", verbose_name="Username")
    first_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Имя")
    last_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Фамилия")
    language_code = models.CharField(max_length=32, blank=True, default="", verbose_name="Код языка")

    full_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Полное имя")
    phone = models.CharField(max_length=64, blank=True, default="", verbose_name="Телефон")
    address = models.CharField(max_length=512, blank=True, default="", verbose_name="Адрес")

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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.client_code:
            return self.client_code
        return str(self.telegram_id)


class Shipment(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Создан"
        IN_CHINA = "in_china", "В Китае"
        ON_THE_WAY = "on_the_way", "В пути"
        ARRIVED = "arrived", "Прибыл"
        DELIVERED = "delivered", "Доставлен"
        NOT_PICKED = "not_picked", "Не забрали"

    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name="shipments",verbose_name="Клиент")
    tracking_number = models.CharField(max_length=128, verbose_name="Трек-номер")
    weight_kg = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True,verbose_name="Вес (кг)",)
    price_per_kg = models.DecimalField(max_digits=12,decimal_places=2,default=0,blank=True,verbose_name="Цена за кг",)
    total_price = models.DecimalField(max_digits=14,decimal_places=2,default=0,blank=True,verbose_name="Итоговая стоимость",)
    status = models.CharField(max_length=32,choices=Status.choices,default=Status.CREATED,verbose_name="Статус",)
    arrival_date = models.DateField(blank=True, null=True, verbose_name="Дата прибытия")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Посылка"
        verbose_name_plural = "Посылки"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.tracking_number


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        TRANSFER = "transfer", "Перевод"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Клиент",
    )
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Посылка",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Сумма")
    method = models.CharField(max_length=16, choices=Method.choices, verbose_name="Метод")
    paid_at = models.DateTimeField(verbose_name="Оплачено")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Оплата"
        verbose_name_plural = "Оплаты"
        ordering = ["-paid_at", "-created_at"]

    def __str__(self) -> str:
        return f"{self.amount}"


class StoragePenalty(models.Model):
    shipment = models.OneToOneField(
        Shipment,
        on_delete=models.CASCADE,
        related_name="storage_penalty",
        verbose_name="Посылка",
    )
    free_days = models.PositiveSmallIntegerField(default=3, verbose_name="Бесплатные дни")
    penalty_per_day = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Штраф за день",
    )
    days_overdue = models.PositiveIntegerField(verbose_name="Просрочено дней")
    total_penalty = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Итоговый штраф",
    )
    calculated_at = models.DateTimeField(verbose_name="Рассчитано")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Штраф за хранение"
        verbose_name_plural = "Штрафы за хранение"
        ordering = ["-calculated_at", "-created_at"]

    def __str__(self) -> str:
        return f"{self.shipment}"

class Staff(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Админ"
        OPERATOR = "operator", "Оператор"
        MANAGER = "manager", "Менеджер"

    user = models.OneToOneField(
        AuthUser,
        on_delete=models.CASCADE,
        related_name="staff_profile",
        verbose_name="Пользователь",
    )
    role = models.CharField(max_length=16, choices=Role.choices, verbose_name="Роль")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = ["role", "-created_at"]

    def __str__(self) -> str:
        return f"{self.user}"


class Notification(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Клиент",
    )
    text = models.TextField(verbose_name="Текст")
    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user}"