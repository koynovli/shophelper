from django.db import migrations, models


def forwards_equipment_types(apps, schema_editor):
    Equipment = apps.get_model("core", "Equipment")
    for eq in Equipment.objects.all():
        if eq.type == "shelf":
            eq.type = "shelving"
            eq.save(update_fields=["type"])


def backwards_equipment_types(apps, schema_editor):
    Equipment = apps.get_model("core", "Equipment")
    for eq in Equipment.objects.all():
        if eq.type == "shelving":
            eq.type = "shelf"
            eq.save(update_fields=["type"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_product_gtin_batch_serial"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipment",
            name="shelf_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Для схематичной отрисовки горизонтальных полок на карте (без связи с моделью Shelf).",
                verbose_name="Число полок (визуализация)",
            ),
        ),
        migrations.RunPython(forwards_equipment_types, backwards_equipment_types),
        migrations.AlterField(
            model_name="equipment",
            name="type",
            field=models.CharField(
                choices=[
                    ("shelving", "Стеллаж"),
                    ("pegboard", "Перфорированная панель"),
                    ("fridge", "Холодильник"),
                    ("pallet", "Паллета"),
                    ("display", "Витрина"),
                ],
                default="shelving",
                help_text="Тип оборудования для отрисовки и логики.",
                max_length=20,
                verbose_name="Тип",
            ),
        ),
        migrations.RenameField(
            model_name="equipment",
            old_name="orientation",
            new_name="rotation",
        ),
    ]
