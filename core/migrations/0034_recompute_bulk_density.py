from __future__ import annotations

from django.db import migrations


def recompute_weight_bulk_density(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    from core.product_units import compute_bulk_density_kg_m3

    for product in Product.objects.filter(sale_unit="weight"):
        bulk = compute_bulk_density_kg_m3(
            product.width,
            product.height,
            product.depth,
            product.weight,
        )
        if bulk is not None:
            Product.objects.filter(pk=product.pk).update(bulk_density=bulk)


def refresh_weight_planogram_capacities(apps, schema_editor):
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
        if live.product.sale_unit != "weight":
            continue
        seen.add(live.slot_id)
        refresh_slot_max_capacity(live.slot, live.product)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_fix_box_shelf_dimensions"),
    ]

    operations = [
        migrations.RunPython(recompute_weight_bulk_density, migrations.RunPython.noop),
        migrations.RunPython(refresh_weight_planogram_capacities, migrations.RunPython.noop),
    ]
