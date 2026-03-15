from django.db import models
from django_resized import ResizedImageField


class PaymentDetails(models.Model):
    """Реквизиты для оплаты по филиалам"""

    filial = models.ForeignKey(
        "Filial",
        on_delete=models.CASCADE,
        related_name="payment_details",
        verbose_name="Филиал",
    )

    # QR код для оплаты
    qr_code = ResizedImageField(
        force_format="WEBP",
        quality=100,
        upload_to="payment/qr/",
        verbose_name="QR код для оплаты",
        blank=True,
        null=True,
    )

    # Дополнительное фото (например, скриншот реквизитов)
    additional_photo = ResizedImageField(
        force_format="WEBP",
        quality=100,
        upload_to="payment/photos/",
        verbose_name="Дополнительное фото",
        blank=True,
        null=True,
    )

    # Банковские реквизиты
    bank_name = models.CharField(max_length=255, verbose_name="Название банка", blank=True, default="")
    account_name = models.CharField(max_length=255, verbose_name="Имя владельца счета", blank=True, default="")
    account_number = models.CharField(max_length=255, verbose_name="Номер счета", blank=True, default="")

    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_primary = models.BooleanField(default=False, verbose_name="Основной (по умолчанию)")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Реквизит для оплаты"
        verbose_name_plural = "Реквизиты для оплаты"
        ordering = ["-is_primary", "-created_at"]

    def __str__(self) -> str:
        return f"{self.filial.name} - {self.bank_name or 'Реквизиты'}"

    def save(self, *args, **kwargs):
        # Если этот реквизит установлен как основной, снимаем флаг с других реквизитов этого филиала
        if self.is_primary:
            PaymentDetails.objects.filter(filial=self.filial, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)
        super().save(*args, **kwargs)
