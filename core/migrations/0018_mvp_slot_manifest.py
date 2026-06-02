# Generated manually for MVP manifest alignment

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def migrate_pending_to_created(apps, schema_editor):
    PlacementTask = apps.get_model("core", "PlacementTask")
    PlacementTask.objects.filter(status="PENDING").update(status="CREATED")


def backfill_slot_capacity(apps, schema_editor):
    EquipmentSlot = apps.get_model("core", "EquipmentSlot")
    Planogram = apps.get_model("core", "Planogram")
    Shelf = apps.get_model("core", "Shelf")
    Product = apps.get_model("core", "Product")

    for slot in EquipmentSlot.objects.all():
        pg = Planogram.objects.filter(slot_id=slot.pk).select_related("product").first()
        if pg is None:
            continue
        product = Product.objects.get(pk=pg.product_id)
        shelf = None
        if slot.shelf_id:
            shelf = Shelf.objects.filter(pk=slot.shelf_id).first()
        if shelf is None:
            shelf = Shelf.objects.filter(
                equipment_id=slot.equipment_id,
                level=slot.row_index + 1,
            ).first()
        if shelf is None:
            continue
        pw, ph, pd = product.width, product.height, product.depth
        if not pw or not ph or not pd:
            continue
        wf = float(slot.width_percent or 100) / 100.0
        sw_mm = float(shelf.width) * 10.0 * wf
        sh_mm = float(shelf.height) * 10.0
        sd_mm = float(shelf.depth) * 10.0
        nx = int(sw_mm // pw)
        ny = int(sd_mm // pd)
        is_stackable = getattr(product, "is_stackable", True)
        nz = int(sh_mm // ph) if is_stackable else 1
        cap = max(0, nx * ny * nz)
        slot.max_capacity = cap
        if pg.target_quantity <= 0 and cap > 0:
            Planogram.objects.filter(pk=pg.pk).update(target_quantity=cap)
        slot.save(update_fields=["max_capacity"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_chat_message_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_stackable",
            field=models.BooleanField(
                default=True,
                help_text="Если False — на полке только один ярус по высоте.",
                verbose_name="Можно штабелировать",
            ),
        ),
        migrations.AddField(
            model_name="equipmentslot",
            name="current_qty",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="Текущий остаток на полке",
            ),
        ),
        migrations.AddField(
            model_name="equipmentslot",
            name="max_capacity",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="Макс. вместимость",
            ),
        ),
        migrations.AddField(
            model_name="equipmentslot",
            name="shelf",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="equipment_slots",
                to="core.shelf",
                verbose_name="Физическая полка",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="placementtask",
            name="uniq_placementtask_pending_planogram",
        ),
        migrations.RunPython(migrate_pending_to_created, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="placementtask",
            name="status",
            field=models.CharField(
                choices=[
                    ("CREATED", "Создана"),
                    ("PENDING", "Ожидает"),
                    ("IN_PROGRESS", "Выполняется"),
                    ("COMPLETED", "Завершено"),
                    ("FAILED", "Проблема"),
                    ("CANCELLED", "Отменена"),
                ],
                default="CREATED",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.AlterField(
            model_name="placementtask",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                help_text="Партия FEFO, подобранная при создании задачи (списание при COMPLETED).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="placement_tasks",
                to="core.productbatch",
                verbose_name="Партия (FEFO)",
            ),
        ),
        migrations.AddConstraint(
            model_name="placementtask",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="CREATED"),
                fields=("planogram",),
                name="uniq_placementtask_created_planogram",
            ),
        ),
        migrations.CreateModel(
            name="PlacementChatMessage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("text", models.TextField(blank=True, verbose_name="Текст")),
                (
                    "image_url",
                    models.URLField(
                        blank=True,
                        max_length=500,
                        null=True,
                        verbose_name="Изображение (URL)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Отправлено"),
                ),
                (
                    "placement_task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="core.placementtask",
                        verbose_name="Задача на выкладку",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="placement_chat_messages",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Отправитель",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сообщение чата (выкладка)",
                "verbose_name_plural": "Сообщения чата (выкладка)",
                "ordering": ("created_at",),
            },
        ),
        migrations.RunPython(backfill_slot_capacity, migrations.RunPython.noop),
    ]
