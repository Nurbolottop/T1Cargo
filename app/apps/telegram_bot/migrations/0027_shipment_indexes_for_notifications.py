from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("telegram_bot", "0026_shipment_issued_at"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="shipment",
            index=models.Index(fields=["group", "filial", "status"], name="shp_grp_fil_status_idx"),
        ),
        migrations.AddIndex(
            model_name="shipment",
            index=models.Index(fields=["group", "user", "filial", "status"], name="shp_grp_usr_fil_st_idx"),
        ),
        migrations.AddIndex(
            model_name="shipment",
            index=models.Index(fields=["user", "filial", "status"], name="shp_usr_fil_status_idx"),
        ),
    ]
