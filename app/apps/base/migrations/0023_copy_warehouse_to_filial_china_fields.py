from django.db import migrations


def copy_warehouse_to_filial(apps, schema_editor):
    Warehouse = apps.get_model("base", "Warehouse")
    Filial = apps.get_model("base", "Filial")

    wh = Warehouse.objects.order_by("name").first()
    if not wh:
        return

    for filial in Filial.objects.all():
        update_fields = []

        if not (getattr(filial, "china_warehouse_name", "") or "").strip():
            filial.china_warehouse_name = (wh.name or "").strip()
            update_fields.append("china_warehouse_name")

        if not (getattr(filial, "china_warehouse_phone", "") or "").strip():
            filial.china_warehouse_phone = (getattr(wh, "phone", "") or "").strip()
            update_fields.append("china_warehouse_phone")

        if not (getattr(filial, "china_warehouse_address", "") or "").strip():
            filial.china_warehouse_address = (wh.address or "").strip()
            update_fields.append("china_warehouse_address")

        if update_fields:
            filial.save(update_fields=update_fields)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0022_filial_china_warehouse_fields"),
    ]

    operations = [
        migrations.RunPython(copy_warehouse_to_filial, reverse_code=noop_reverse),
    ]
