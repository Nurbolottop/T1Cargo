from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0017_delete_instruction"),
    ]

    operations = [
        migrations.AlterField(
            model_name="settings",
            name="prohibited_goods_text",
            field=models.TextField(blank=True, verbose_name="Запрещенные товары (текст)"),
        ),
        migrations.AlterField(
            model_name="filial",
            name="wholesale_order_text",
            field=models.TextField(blank=True, verbose_name="Оптовый заказ (текст)"),
        ),
        migrations.AddField(
            model_name="filial",
            name="wholesale_whatsapp_phone",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="WhatsApp (оптовые товары)"),
        ),
    ]
