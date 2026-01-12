from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("telegram_bot", "0015_alter_userssh_managers"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShipmentGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True, verbose_name="Название группы")),
                ("status", models.CharField(choices=[("on_the_way", "В пути"), ("bishkek", "В Бишкеке"), ("warehouse", "На складе"), ("issued", "Выдано")], default="on_the_way", max_length=32, verbose_name="Статус группы")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Группа",
                "verbose_name_plural": "Группы",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AlterField(
            model_name="shipment",
            name="user",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shipments", verbose_name="Клиент", to="telegram_bot.user"),
        ),
        migrations.AddField(
            model_name="shipment",
            name="group",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shipments", to="telegram_bot.shipmentgroup", verbose_name="Группа"),
        ),
        migrations.AddField(
            model_name="shipment",
            name="client_code_raw",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Код клиента (из импорта)"),
        ),
        migrations.AddField(
            model_name="shipment",
            name="import_status",
            field=models.CharField(choices=[("ok", "Ок"), ("no_client_code", "Неизвестный клиент"), ("client_not_found", "Клиент не найден")], default="ok", max_length=32, verbose_name="Статус импорта"),
        ),
    ]
