from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0023_copy_warehouse_to_filial_china_fields"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Warehouse",
        ),
    ]
