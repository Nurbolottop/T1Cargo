from django.db import models
from django_resized import ResizedImageField
# Create your models here.

try:
    from ckeditor.fields import RichTextField
except Exception:
    RichTextField = models.TextField

class Settings(models.Model):
    title = models.CharField(max_length=255, verbose_name="Название карго")
    manager_contact = models.CharField(max_length=255, verbose_name="Контакт менеджера", blank=True)
    instagram_url = models.URLField(verbose_name="Instagram URL", blank=True)
    phone = models.CharField(max_length=255, verbose_name="Телефон", blank=True)
    work_hours = models.CharField(max_length=255, verbose_name="Режим работы", blank=True)
    pvz_location_url = models.URLField(verbose_name="Локация ПВЗ (ссылка на карту)", blank=True)
    email = models.EmailField(verbose_name="Email", blank=True)
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

    currency = models.CharField(max_length=16, verbose_name="Валюта", blank=True, default="KGS")
    default_price_per_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Цена по умолчанию за кг",
        blank=True,
        null=True,
    )

    is_site_enabled = models.BooleanField(default=True, verbose_name="Сайт включен")
    is_bot_enabled = models.BooleanField(default=True, verbose_name="Бот включен")

    prohibited_goods_text = RichTextField(verbose_name="Запрещенные товары (текст)", blank=True)

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


class Warehouse(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    country = models.CharField(max_length=128, verbose_name="Страна")
    city = models.CharField(max_length=128, verbose_name="Город")
    address = models.CharField(max_length=512, verbose_name="Адрес")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "2) Склад"
        verbose_name_plural = "2) Склады"
        ordering = ["name", "country", "city"]

    def __str__(self) -> str:
        return self.name


class Instruction(models.Model):
    title = models.CharField(max_length=255, verbose_name="Заголовок")
    text = RichTextField(verbose_name="Инструкция")
    photo = ResizedImageField(
        force_format="WEBP",
        quality=100,
        upload_to="instructions/",
        verbose_name="Фото",
        blank=True,
        null=True,
    )
    video_url = models.URLField(verbose_name="Ссылка на видео", blank=True)
    link_url = models.URLField(verbose_name="Ссылка", blank=True)
    file = models.FileField(upload_to="instructions/", verbose_name="Файл", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "3) Инструкция"
        verbose_name_plural = "3) Инструкции"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title