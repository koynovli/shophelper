import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_mvp_slot_manifest"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShelfWriteOff",
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
                ("quantity", models.PositiveIntegerField(verbose_name="Списано, шт.")),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            (
                                "EXPIRED_PLACEMENT_BATCH",
                                "Просрочена партия последней выкладки",
                            )
                        ],
                        default="EXPIRED_PLACEMENT_BATCH",
                        max_length=40,
                        verbose_name="Причина",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Создано"),
                ),
                (
                    "batch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="shelf_write_offs",
                        to="core.productbatch",
                        verbose_name="Партия",
                    ),
                ),
                (
                    "placement_task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="shelf_write_offs",
                        to="core.placementtask",
                        verbose_name="Задача выкладки",
                    ),
                ),
                (
                    "planogram",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="write_offs",
                        to="core.planogram",
                        verbose_name="Планограмма",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shelf_write_offs",
                        to="core.product",
                        verbose_name="Товар",
                    ),
                ),
                (
                    "slot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="write_offs",
                        to="core.equipmentslot",
                        verbose_name="Слот",
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shelf_write_offs",
                        to="core.store",
                        verbose_name="Магазин",
                    ),
                ),
            ],
            options={
                "verbose_name": "Списание с полки",
                "verbose_name_plural": "Списания с полок",
                "ordering": ("-created_at",),
            },
        ),
    ]
