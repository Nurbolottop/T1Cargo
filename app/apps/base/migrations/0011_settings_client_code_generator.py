from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0010_settings_pvz_location_url_settings_work_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="settings",
            name="client_code_prefix",
            field=models.CharField(blank=True, default="T1", max_length=16, verbose_name="Префикс кода клиента"),
        ),
        migrations.AddField(
            model_name="settings",
            name="client_code_start_number",
            field=models.PositiveIntegerField(default=1000, verbose_name="Стартовый номер кода клиента"),
        ),
        migrations.AddField(
            model_name="settings",
            name="client_code_last_number",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Последний выданный номер кода клиента"),
        ),
    ]
