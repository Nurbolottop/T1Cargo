from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0011_settings_client_code_generator"),
    ]

    operations = [
        migrations.CreateModel(
            name="Filial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("city", models.CharField(max_length=128, verbose_name="Город")),
                ("address", models.CharField(blank=True, default="", max_length=512, verbose_name="Адрес")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("client_code_prefix", models.CharField(blank=True, default="T1", max_length=16, verbose_name="Префикс кода клиента")),
                ("client_code_start_number", models.PositiveIntegerField(default=1000, verbose_name="Стартовый номер кода клиента")),
                ("client_code_last_number", models.PositiveIntegerField(blank=True, null=True, verbose_name="Последний выданный номер кода клиента")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "4) Филиал",
                "verbose_name_plural": "4) Филиалы",
                "ordering": ["city", "name"],
            },
        ),
    ]
