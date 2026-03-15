from django.db import models
from django_resized import ResizedImageField
# Create your models here.

try:
    from ckeditor.fields import RichTextField
except Exception:
    RichTextField = models.TextField

class Settings(models.Model):
    title = models.CharField(max_length=255, verbose_name="Название карго")
    phone = models.CharField(max_length=255, verbose_name="Телефон", blank=True)
    website = models.URLField(verbose_name="Сайт", blank=True)
    registration_webapp_url = models.URLField(verbose_name="Ссылка на регистрацию (Telegram WebApp)", blank=True)
    logo = ResizedImageField(
        force_format="WEBP",
        quality=100,
        upload_to="logo/",
        verbose_name="Логотип карго",
        blank=True,
        null=True,
    )
    icon = ResizedImageField(
        force_format="WEBP",
        quality=100,
        upload_to="logo/",
        verbose_name="Иконка карго",
        blank=True,
        null=True,
    )

    telegram_token = models.CharField(max_length=255, verbose_name="Токен телеграм", blank=True)
    telegram_bot_username = models.CharField(max_length=255, verbose_name="Username бота", blank=True)

    is_site_enabled = models.BooleanField(default=True, verbose_name="Сайт включен")
    is_bot_enabled = models.BooleanField(default=True, verbose_name="Бот включен")

    prohibited_goods_text = models.TextField(verbose_name="Запрещенные товары (текст)", blank=True)

    # Реквизиты для оплаты
    payment_qr_code = ResizedImageField(
        force_format="WEBP",
        quality=100,
        upload_to="payment/",
        verbose_name="QR код для оплаты",
        blank=True,
        null=True,
    )
    payment_account_name = models.CharField(max_length=255, verbose_name="Имя владельца счета", blank=True, default="")
    payment_account_number = models.CharField(max_length=255, verbose_name="Номер счета", blank=True, default="")
    payment_bank_name = models.CharField(max_length=255, verbose_name="Название банка", blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "1) Основные настройка"
        verbose_name_plural = "1) Основные настройки"

    def __str__(self) -> str:
        return self.title


class AdminId(models.Model):
    settings = models.OneToOneField(
        Settings,
        on_delete=models.CASCADE,
        related_name="admin",
        verbose_name="Настройки",
    )
    admin_id = models.CharField(max_length=255, verbose_name="ID администратора")

    def __str__(self) -> str:
        return self.admin_id

    class Meta:
        verbose_name = "ID администратора"
        verbose_name_plural = "ID администраторов"


class Filial(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    city = models.CharField(max_length=128, verbose_name="Город")
    address = models.CharField(max_length=512, verbose_name="Адрес", blank=True, default="")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    manager_contact = models.CharField(max_length=255, verbose_name="Контакт менеджера", blank=True, default="")
    instagram_url = models.URLField(verbose_name="Instagram URL", blank=True, default="")
    email = models.EmailField(verbose_name="Email", blank=True, default="")
    work_hours = models.TextField(verbose_name="Режим работы", blank=True)
    pvz_location_url = models.URLField(verbose_name="Локация ПВЗ (ссылка на карту)", blank=True, default="")

    china_warehouse_name = models.CharField(
        max_length=255,
        verbose_name="Склад в Китае (название)",
        blank=True,
        default="",
    )
    china_warehouse_phone = models.CharField(
        max_length=64,
        verbose_name="Склад в Китае (телефон)",
        blank=True,
        default="",
    )
    china_warehouse_address = models.CharField(
        max_length=512,
        verbose_name="Склад в Китае (адрес)",
        blank=True,
        default="",
    )

    currency = models.CharField(max_length=16, verbose_name="Валюта", blank=True, default="KGS")
    default_price_per_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Цена по умолчанию за кг",
        blank=True,
        null=True,
    )

    storage_penalty_per_day = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Штраф за хранение (в день)",
        blank=True,
        null=True,
    )

    wholesale_order_text = models.TextField(verbose_name="Оптовый заказ (текст)", blank=True)
    wholesale_whatsapp_phone = models.CharField(
        max_length=32,
        verbose_name="WhatsApp (оптовые товары)",
        blank=True,
        default="",
    )

    client_code_prefix = models.CharField(
        max_length=16,
        verbose_name="Префикс кода клиента",
        blank=True,
        default="T1",
    )

    china_client_code_prefix = models.CharField(
        max_length=16,
        verbose_name="Префикс кода клиента (Китай)",
        blank=True,
        default="阿",
    )
    client_code_start_number = models.PositiveIntegerField(
        verbose_name="Стартовый номер кода клиента",
        default=1000,
    )
    client_code_last_number = models.PositiveIntegerField(
        verbose_name="Последний выданный номер кода клиента",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "4) Филиал"
        verbose_name_plural = "4) Филиалы"
        ordering = ["city", "name"]

    def __str__(self) -> str:
        return f"{self.city} — {self.name}"