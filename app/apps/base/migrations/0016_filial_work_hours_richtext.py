import ckeditor.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0015_filial_wholesale_order_text"),
    ]

    operations = [
        migrations.AlterField(
            model_name="filial",
            name="work_hours",
            field=ckeditor.fields.RichTextField(blank=True, verbose_name="Режим работы"),
        ),
    ]
