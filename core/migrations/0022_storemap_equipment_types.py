from django.db import migrations, models
import django.db.models.deletion


def rename_equipment_types(apps, schema_editor):
    Equipment = apps.get_model("core", "Equipment")
    mapping = {
        "shelving": "shelf",
        "pegboard": "hanger",
        "pallet": "box",
        "display": "mannequin",
    }
    for old, new in mapping.items():
        Equipment.objects.filter(type=old).update(type=new)


def seed_store_maps(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    StoreMap = apps.get_model("core", "StoreMap")
    for store in Store.objects.all():
        StoreMap.objects.get_or_create(
            store_id=store.id,
            defaults={"width_m": 20.0, "length_m": 15.0},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_supplyorder_planned_receiving_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="StoreMap",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "width_m",
                    models.FloatField(
                        default=20.0,
                        help_text="Ширина торгового зала на плане в метрах.",
                        verbose_name="Ширина зала (м)",
                    ),
                ),
                (
                    "length_m",
                    models.FloatField(
                        default=15.0,
                        help_text="Длина торгового зала на плане в метрах.",
                        verbose_name="Длина зала (м)",
                    ),
                ),
                (
                    "store",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="floor_map",
                        to="core.store",
                        verbose_name="Магазин",
                    ),
                ),
            ],
            options={
                "verbose_name": "План зала",
                "verbose_name_plural": "Планы зала",
            },
        ),
        migrations.RunPython(rename_equipment_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="equipment",
            name="type",
            field=models.CharField(
                choices=[
                    ("shelf", "Стеллаж"),
                    ("hanger", "Вешалка"),
                    ("fridge", "Холодильник"),
                    ("box", "Бокс / корзина"),
                    ("mannequin", "Манекен / промо-стенд"),
                ],
                default="shelf",
                help_text="Тип оборудования для отрисовки и логики.",
                max_length=20,
                verbose_name="Тип",
            ),
        ),
        migrations.RunPython(seed_store_maps, migrations.RunPython.noop),
    ]
