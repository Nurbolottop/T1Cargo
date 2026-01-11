import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0012_filial"),
        ("telegram_bot", "0005_delete_warehouse_alter_shipment_price_per_kg_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="filial",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="clients",
                to="base.filial",
                verbose_name="Филиал",
            ),
        ),
    ]
