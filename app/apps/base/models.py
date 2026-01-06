from django.db import models
from django_resized import ResizedImageField
# Create your models here.

class AdminId(models.Model):
    admin_id = models.CharField(max_length=255, verbose_name="ID администратора")

class Settings(models.Model):
    title = models.CharField(max_length=255, verbose_name="Название карго")
    manager_contact = models.CharField(max_length=255, verbose_name="Контакт менеджера", blank=True)
    phone = models.CharField(max_length=255, verbose_name="Телефон", blank=True)
    email = models.EmailField(verbose_name="Email", blank=True)
    website = models.URLField(verbose_name="Сайт", blank=True)
    admin_id = models.ForeignKey(AdminId, on_delete=models.CASCADE, verbose_name="ID администратора", related_name="settings")
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройка"
        verbose_name_plural = "Настройки"

    def __str__(self) -> str:
        return self.title 