from __future__ import annotations

from .models import Equipment, EquipmentSlot, Product, Shelf

BULK_FILL_FACTOR = 0.8
HANGER_GAP_MM = 15.0


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


def calculate_linear_hanger_capacity(
    shelf_width_cm: float,
    product: Product,
    *,
    width_fraction: float = 1.0,
) -> int:
    """Вешалка: ширина рейла / (толщина изделия + зазор), без штабелирования."""
    if product is None or not product.depth or product.depth <= 0:
        return 0
    sw_mm = float(shelf_width_cm) * 10.0 * max(0.0, min(1.0, width_fraction))
    unit = float(product.depth) + HANGER_GAP_MM
    return max(0, int(sw_mm // unit))


def calculate_bulk_box_capacity(
    shelf_width_cm: float,
    shelf_height_cm: float,
    shelf_depth_cm: float,
    product: Product,
    *,
    width_fraction: float = 1.0,
) -> int:
    """Бокс: объём с коэффициентом пустот / объём единицы товара."""
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
    box_vol = sw_mm * sh_mm * sd_mm
    unit_vol = float(pw) * float(ph) * float(pd)
    if unit_vol <= 0:
        return 0
    return max(0, int((box_vol * BULK_FILL_FACTOR) // unit_vol))


def resolve_shelf_for_slot(slot: EquipmentSlot) -> Shelf | None:
    if slot.shelf_id:
        return slot.shelf
    return (
        Shelf.objects.filter(
            equipment_id=slot.equipment_id,
            level=slot.row_index + 1,
        ).first()
    )


def _equipment_type_for_slot(slot: EquipmentSlot) -> str:
    if getattr(slot, "equipment_id", None) and hasattr(slot, "equipment"):
        try:
            return str(slot.equipment.type)
        except Equipment.DoesNotExist:
            pass
    found = (
        Equipment.objects.filter(pk=slot.equipment_id)
        .values_list("type", flat=True)
        .first()
    )
    return str(found or Equipment.EquipmentType.SHELF)


def calculate_slot_max_capacity(slot: EquipmentSlot, product: Product) -> int:
    shelf = resolve_shelf_for_slot(slot)
    if shelf is None:
        return 0
    width_fraction = float(slot.width_percent or 100.0) / 100.0
    eq_type = _equipment_type_for_slot(slot)

    if eq_type == Equipment.EquipmentType.MANNEQUIN:
        return 1

    if eq_type == Equipment.EquipmentType.BOX:
        return calculate_bulk_box_capacity(
            shelf.width,
            shelf.height,
            shelf.depth,
            product,
            width_fraction=width_fraction,
        )

    if eq_type == Equipment.EquipmentType.HANGER:
        return calculate_linear_hanger_capacity(
            shelf.width,
            product,
            width_fraction=width_fraction,
        )

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
