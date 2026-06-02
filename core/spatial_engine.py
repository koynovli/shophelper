from __future__ import annotations

from .models import EquipmentSlot, Product, Shelf


def calculate_max_capacity_from_dimensions(
    shelf_width_cm: float,
    shelf_height_cm: float,
    shelf_depth_cm: float,
    product: Product,
    *,
    width_fraction: float = 1.0,
) -> int:
    """
    Дискретная укладка: ряды по ширине × глубине × ярусы по высоте.
    width_fraction — доля ширины ряда, занимаемая слотом (0..1).
    """
    if product is None:
        return 0
    pw, ph, pd = product.width, product.height, product.depth
    if not pw or not ph or not pd or pw <= 0 or ph <= 0 or pd <= 0:
        return 0
    if shelf_width_cm <= 0 or shelf_height_cm <= 0 or shelf_depth_cm <= 0:
        return 0

    sw_mm = float(shelf_width_cm) * 10.0 * max(0.0, min(1.0, width_fraction))
    sh_mm = float(shelf_height_cm) * 10.0
    sd_mm = float(shelf_depth_cm) * 10.0

    nx = int(sw_mm // pw)
    ny = int(sd_mm // pd)
    if getattr(product, "is_stackable", True):
        nz = int(sh_mm // ph)
    else:
        nz = 1

    return max(0, nx * ny * nz)


def resolve_shelf_for_slot(slot: EquipmentSlot) -> Shelf | None:
    if slot.shelf_id:
        return slot.shelf
    return (
        Shelf.objects.filter(
            equipment_id=slot.equipment_id,
            level=slot.row_index + 1,
        ).first()
    )


def calculate_slot_max_capacity(slot: EquipmentSlot, product: Product) -> int:
    shelf = resolve_shelf_for_slot(slot)
    if shelf is None:
        return 0
    width_fraction = float(slot.width_percent or 100.0) / 100.0
    return calculate_max_capacity_from_dimensions(
        shelf.width,
        shelf.height,
        shelf.depth,
        product,
        width_fraction=width_fraction,
    )


def refresh_slot_max_capacity(slot: EquipmentSlot, product: Product | None = None) -> int:
    """Пересчитывает и сохраняет max_capacity слота для товара планограммы."""
    if product is None:
        pg = slot.planograms.select_related("product").first()
        if pg is None:
            slot.max_capacity = 0
            slot.save(update_fields=["max_capacity"])
            return 0
        product = pg.product
    cap = calculate_slot_max_capacity(slot, product)
    if slot.max_capacity != cap:
        slot.max_capacity = cap
        slot.save(update_fields=["max_capacity"])
    return cap
