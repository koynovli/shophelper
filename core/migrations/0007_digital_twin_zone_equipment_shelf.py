# Manual migration: переименование планограммного Equipment в PlanogramEquipment
# и добавление моделей цифрового двойника (Zone, Equipment, Shelf).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_supplier_scm_finance"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Equipment",
            new_name="PlanogramEquipment",
        ),
        migrations.CreateModel(
            name="Zone",
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
                    "name",
                    models.CharField(
                        help_text="Например: «Торговый зал», «Склад».",
                        max_length=255,
                        verbose_name="Название",
                    ),
                ),
                (
                    "color",
                    models.CharField(
                        help_text="Цвет отображения зоны (например, HEX-код #RRGGBB).",
                        max_length=32,
                        verbose_name="Цвет на карте",
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        help_text="Магазин, к которому относится зона на плане.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="zones",
                        to="core.store",
                        verbose_name="Магазин",
                    ),
                ),
            ],
            options={
                "verbose_name": "Зона",
                "verbose_name_plural": "Зоны",
            },
        ),
        migrations.CreateModel(
            name="Equipment",
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
                    "name",
                    models.CharField(
                        help_text="Например: «Стеллаж №1».",
                        max_length=255,
                        verbose_name="Название",
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("shelf", "Стеллаж"),
                            ("fridge", "Холодильник"),
                            ("display", "Витрина"),
                        ],
                        default="shelf",
                        help_text="Тип оборудования для отрисовки и логики.",
                        max_length=20,
                        verbose_name="Тип",
                    ),
                ),
                (
                    "pos_x",
                    models.FloatField(
                        help_text="Координата X центра объекта на плане.",
                        verbose_name="Позиция X (центр)",
                    ),
                ),
                (
                    "pos_y",
                    models.FloatField(
                        help_text="Координата Y центра объекта на плане.",
                        verbose_name="Позиция Y (центр)",
                    ),
                ),
                (
                    "width",
                    models.FloatField(
                        help_text="Ширина объекта на плане (условные единицы или см — по договорённости).",
                        verbose_name="Ширина",
                    ),
                ),
                (
                    "height",
                    models.FloatField(
                        help_text="Высота объекта на плане (условные единицы или см — по договорённости).",
                        verbose_name="Высота",
                    ),
                ),
                (
                    "orientation",
                    models.FloatField(
                        default=0.0,
                        help_text="Угол поворота объекта на плане в градусах.",
                        verbose_name="Поворот (°)",
                    ),
                ),
                (
                    "zone",
                    models.ForeignKey(
                        help_text="Зона торгового зала или склада, где стоит объект.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="equipment",
                        to="core.zone",
                        verbose_name="Зона",
                    ),
                ),
            ],
            options={
                "verbose_name": "Оборудование (план зала)",
                "verbose_name_plural": "Оборудование (план зала)",
            },
        ),
        migrations.CreateModel(
            name="Shelf",
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
                    "level",
                    models.PositiveIntegerField(
                        help_text="Номер полки снизу вверх (1 — нижняя).",
                        verbose_name="Номер полки",
                    ),
                ),
                (
                    "width",
                    models.FloatField(
                        help_text="Внутренняя ширина полки в сантиметрах.",
                        verbose_name="Ширина (см)",
                    ),
                ),
                (
                    "height",
                    models.FloatField(
                        help_text="Внутренняя высота полки в сантиметрах.",
                        verbose_name="Высота (см)",
                    ),
                ),
                (
                    "depth",
                    models.FloatField(
                        help_text="Внутренняя глубина полки в сантиметрах.",
                        verbose_name="Глубина (см)",
                    ),
                ),
                (
                    "capacity_notes",
                    models.TextField(
                        blank=True,
                        help_text="Дополнительная информация о грузоподъёмности, шаге крючков и т.п.",
                        verbose_name="Примечания по вместимости",
                    ),
                ),
                (
                    "equipment",
                    models.ForeignKey(
                        help_text="Стеллаж/витрина/холодильник, к которому относится полка.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shelves",
                        to="core.equipment",
                        verbose_name="Оборудование",
                    ),
                ),
            ],
            options={
                "verbose_name": "Полка",
                "verbose_name_plural": "Полки",
            },
        ),
        migrations.AddConstraint(
            model_name="shelf",
            constraint=models.UniqueConstraint(
                fields=("equipment", "level"),
                name="uniq_shelf_equipment_level",
            ),
        ),
        migrations.AddField(
            model_name="inventory",
            name="shelf",
            field=models.ForeignKey(
                blank=True,
                help_text="Приоритетная привязка к полке цифрового двойника зала (если указана).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="inventories",
                to="core.shelf",
                verbose_name="Полка (план зала)",
            ),
        ),
        migrations.AlterModelOptions(
            name="planogramequipment",
            options={
                "verbose_name": "Оборудование (планограмма)",
                "verbose_name_plural": "Оборудование (планограмма)",
            },
        ),
    ]
