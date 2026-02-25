from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("telegram_bot", "0027_shipment_indexes_for_notifications"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="shipment",
            index=models.Index(fields=["group", "tracking_number"], name="shp_grp_tracking_idx"),
        ),
        migrations.AddIndex(
            model_name="shipment",
            index=models.Index(fields=["tracking_number"], name="shp_tracking_idx"),
        ),
    ]
