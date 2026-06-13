from django.db import migrations, models


MANNEQUIN_LABELS = ("Верх", "Низ", "Аксессуар")


def _normalize_type(eq_type):
    mapping = {
        "shelving": "shelf",
        "pegboard": "hanger",
        "pallet": "box",
        "display": "mannequin",
    }
    return mapping.get(eq_type, eq_type)


def rebuild_non_grid_slots(apps, schema_editor):
    Equipment = apps.get_model("core", "Equipment")
    EquipmentSlot = apps.get_model("core", "EquipmentSlot")
    Planogram = apps.get_model("core", "Planogram")

    for equipment in Equipment.objects.all():
        eq_type = _normalize_type(str(equipment.type))
        if eq_type in ("shelf", "fridge"):
            continue

        slots = list(
            EquipmentSlot.objects.filter(equipment_id=equipment.id).order_by(
                "row_index", "col_index"
            )
        )
        planogram_slot_ids = set(
            Planogram.objects.filter(slot__equipment_id=equipment.id).values_list(
                "slot_id", flat=True
            )
        )

        if eq_type == "box":
            target_specs = [(0, 0, 100.0, "")]
        elif eq_type == "hanger":
            rows = min(max(int(equipment.rows_count or 0), 1), 2)
            target_specs = [(r, 0, 100.0, "") for r in range(rows)]
        elif eq_type == "mannequin":
            target_specs = [
                (i, 0, 100.0, MANNEQUIN_LABELS[i] if i < len(MANNEQUIN_LABELS) else "")
                for i in range(3)
            ]
        else:
            continue

        if not planogram_slot_ids:
            EquipmentSlot.objects.filter(equipment_id=equipment.id).delete()
            for row, col, width, label in target_specs:
                EquipmentSlot.objects.create(
                    equipment_id=equipment.id,
                    row_index=row,
                    col_index=col,
                    width_percent=width,
                    slot_label=label,
                )
            continue

        keep = None
        for slot in slots:
            if slot.id in planogram_slot_ids:
                keep = slot
                break
        if keep is None and slots:
            keep = slots[0]

        EquipmentSlot.objects.filter(equipment_id=equipment.id).exclude(
            pk=keep.pk if keep else -1
        ).delete()

        existing_keys = set(
            EquipmentSlot.objects.filter(equipment_id=equipment.id).values_list(
                "row_index", "col_index"
            )
        )
        for row, col, width, label in target_specs:
            if (row, col) in existing_keys:
                EquipmentSlot.objects.filter(
                    equipment_id=equipment.id,
                    row_index=row,
                    col_index=col,
                ).update(width_percent=width, slot_label=label)
            else:
                EquipmentSlot.objects.create(
                    equipment_id=equipment.id,
                    row_index=row,
                    col_index=col,
                    width_percent=width,
                    slot_label=label,
                )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_storemap_equipment_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipmentslot",
            name="slot_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Например: «Верх» для зоны экспозиции на манекене.",
                max_length=64,
                verbose_name="Подпись зоны",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="allowed_equipment_types",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Пустой список — без ограничения. Иначе whitelist типов выкладки.",
                verbose_name="Допустимые типы оборудования",
            ),
        ),
        migrations.RunPython(rebuild_non_grid_slots, migrations.RunPython.noop),
    ]
