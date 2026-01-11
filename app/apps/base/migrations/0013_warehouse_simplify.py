from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0012_filial"),
    ]

    operations = [
        migrations.AddField(
            model_name="warehouse",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Телефон"),
        ),
        migrations.RemoveField(
            model_name="warehouse",
            name="country",
        ),
        migrations.RemoveField(
            model_name="warehouse",
            name="city",
        ),
        migrations.AlterModelOptions(
            name="warehouse",
            options={"ordering": ["name"], "verbose_name": "2) Склад", "verbose_name_plural": "2) Склады"},
        ),
    ]
