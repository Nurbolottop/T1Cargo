from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0016_filial_work_hours_richtext"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Instruction",
        ),
    ]
