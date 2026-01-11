from django.db import migrations, models


def _copy_settings_to_filials(apps, schema_editor):
    Settings = apps.get_model("base", "Settings")
    Filial = apps.get_model("base", "Filial")

    settings_obj = Settings.objects.first()
    if not settings_obj:
        return

    update_fields = [
        "manager_contact",
        "instagram_url",
        "email",
        "work_hours",
        "pvz_location_url",
        "currency",
        "default_price_per_kg",
    ]

    for filial in Filial.objects.all():
        filial.manager_contact = getattr(settings_obj, "manager_contact", "") or ""
        filial.instagram_url = getattr(settings_obj, "instagram_url", "") or ""
        filial.email = getattr(settings_obj, "email", "") or ""
        filial.work_hours = getattr(settings_obj, "work_hours", "") or ""
        filial.pvz_location_url = getattr(settings_obj, "pvz_location_url", "") or ""
        filial.currency = getattr(settings_obj, "currency", "KGS") or "KGS"
        filial.default_price_per_kg = getattr(settings_obj, "default_price_per_kg", None)
        filial.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0013_warehouse_simplify"),
    ]

    operations = [
        migrations.AddField(
            model_name="filial",
            name="manager_contact",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Контакт менеджера"),
        ),
        migrations.AddField(
            model_name="filial",
            name="instagram_url",
            field=models.URLField(blank=True, default="", verbose_name="Instagram URL"),
        ),
        migrations.AddField(
            model_name="filial",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254, verbose_name="Email"),
        ),
        migrations.AddField(
            model_name="filial",
            name="work_hours",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Режим работы"),
        ),
        migrations.AddField(
            model_name="filial",
            name="pvz_location_url",
            field=models.URLField(blank=True, default="", verbose_name="Локация ПВЗ (ссылка на карту)"),
        ),
        migrations.AddField(
            model_name="filial",
            name="currency",
            field=models.CharField(blank=True, default="KGS", max_length=16, verbose_name="Валюта"),
        ),
        migrations.AddField(
            model_name="filial",
            name="default_price_per_kg",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="Цена по умолчанию за кг",
            ),
        ),
        migrations.RunPython(_copy_settings_to_filials, migrations.RunPython.noop),
        migrations.RemoveField(model_name="settings", name="manager_contact"),
        migrations.RemoveField(model_name="settings", name="instagram_url"),
        migrations.RemoveField(model_name="settings", name="email"),
        migrations.RemoveField(model_name="settings", name="work_hours"),
        migrations.RemoveField(model_name="settings", name="pvz_location_url"),
        migrations.RemoveField(model_name="settings", name="currency"),
        migrations.RemoveField(model_name="settings", name="default_price_per_kg"),
        migrations.RemoveField(model_name="settings", name="client_code_prefix"),
        migrations.RemoveField(model_name="settings", name="client_code_start_number"),
        migrations.RemoveField(model_name="settings", name="client_code_last_number"),
    ]
