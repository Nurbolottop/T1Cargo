from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0021_filial_china_client_code_prefix"),
    ]

    operations = [
        migrations.AddField(
            model_name="filial",
            name="china_warehouse_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Склад в Китае (название)"),
        ),
        migrations.AddField(
            model_name="filial",
            name="china_warehouse_phone",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Склад в Китае (телефон)"),
        ),
        migrations.AddField(
            model_name="filial",
            name="china_warehouse_address",
            field=models.CharField(blank=True, default="", max_length=512, verbose_name="Склад в Китае (адрес)"),
        ),
    ]
