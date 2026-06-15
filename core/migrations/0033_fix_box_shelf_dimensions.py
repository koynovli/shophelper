from __future__ import annotations

from django.db import migrations


def resync_box_shelf_dimensions(apps, schema_editor):
    Equipment = apps.get_model("core", "Equipment")
    from core.equipment_layout_sync import resync_equipment_shelves
    from core.equipment_profiles import normalize_equipment_type
    from core.models import Equipment as LiveEquipment

    box_types = {LiveEquipment.EquipmentType.BOX, "pallet"}
    for eq in Equipment.objects.all():
        if normalize_equipment_type(str(eq.type)) not in box_types:
            continue
        live = LiveEquipment.objects.filter(pk=eq.pk).first()
        if live is not None:
            resync_equipment_shelves(live)


def refresh_box_capacities(apps, schema_editor):
    Planogram = apps.get_model("core", "Planogram")
    from core.models import Planogram as LivePlanogram
    from core.spatial_engine import refresh_slot_max_capacity

    seen: set[int] = set()
    for pg_id in Planogram.objects.values_list("pk", flat=True):
        live = (
            LivePlanogram.objects.filter(pk=pg_id)
            .select_related("slot", "product")
            .first()
        )
        if live is None or live.slot_id in seen:
            continue
        seen.add(live.slot_id)
        refresh_slot_max_capacity(live.slot, live.product)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_product_packing_physics"),
    ]

    operations = [
        migrations.RunPython(resync_box_shelf_dimensions, migrations.RunPython.noop),
        migrations.RunPython(refresh_box_capacities, migrations.RunPython.noop),
    ]
