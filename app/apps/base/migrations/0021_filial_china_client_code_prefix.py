from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0020_filial_storage_penalty_per_day"),
    ]

    operations = [
        migrations.AddField(
            model_name="filial",
            name="china_client_code_prefix",
            field=models.CharField(blank=True, default="阿", max_length=16, verbose_name="Префикс кода клиента (Китай)"),
        ),
    ]
