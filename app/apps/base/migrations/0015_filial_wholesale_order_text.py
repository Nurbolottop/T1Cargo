import ckeditor.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0014_filial_fields_move_from_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="filial",
            name="wholesale_order_text",
            field=ckeditor.fields.RichTextField(blank=True, verbose_name="Оптовый заказ (текст)"),
        ),
    ]
