from __future__ import annotations

from .equipment_profiles import virtual_shelf_dimensions_for_slot
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
    force_single_layer: bool = False,
) -> int:
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
    stackable = getattr(product, "is_stackable", True) and not force_single_layer
    if stackable:
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


def _get_equipment_for_slot(slot: EquipmentSlot) -> Equipment | None:
    if hasattr(slot, "equipment") and slot.equipment_id:
        try:
            return slot.equipment
        except Equipment.DoesNotExist:
            pass
    return Equipment.objects.filter(pk=slot.equipment_id).first()


def resolve_shelf_for_slot(slot: EquipmentSlot) -> Shelf | None:
    equipment = _get_equipment_for_slot(slot)
    if equipment and str(equipment.type) == Equipment.EquipmentType.MANNEQUIN:
        return None
    if slot.shelf_id:
        return slot.shelf
    return (
        Shelf.objects.filter(
            equipment_id=slot.equipment_id,
            level=slot.row_index + 1,
        ).first()
    )


def _equipment_type_for_slot(slot: EquipmentSlot) -> str:
    equipment = _get_equipment_for_slot(slot)
    if equipment:
        return str(equipment.type)
    found = (
        Equipment.objects.filter(pk=slot.equipment_id)
        .values_list("type", flat=True)
        .first()
    )
    return str(found or Equipment.EquipmentType.SHELF)


def _dimensions_for_capacity(slot: EquipmentSlot, equipment: Equipment | None) -> tuple[float, float, float] | None:
    shelf = resolve_shelf_for_slot(slot)
    if shelf is not None:
        return float(shelf.width), float(shelf.height), float(shelf.depth)
    if equipment is None:
        equipment = _get_equipment_for_slot(slot)
    if equipment is None:
        return None
    virtual = virtual_shelf_dimensions_for_slot(slot, equipment)
    if virtual is None:
        return None
    return virtual["width"], virtual["height"], virtual["depth"]


def calculate_slot_max_capacity(slot: EquipmentSlot, product: Product) -> int:
    equipment = _get_equipment_for_slot(slot)
    eq_type = _equipment_type_for_slot(slot)
    width_fraction = float(slot.width_percent or 100.0) / 100.0

    if eq_type == Equipment.EquipmentType.MANNEQUIN:
        return 1

    dims = _dimensions_for_capacity(slot, equipment)
    if dims is None:
        return 0
    sw, sh, sd = dims

    if eq_type == Equipment.EquipmentType.BOX:
        return calculate_bulk_box_capacity(sw, sh, sd, product, width_fraction=width_fraction)

    if eq_type == Equipment.EquipmentType.HANGER:
        return calculate_linear_hanger_capacity(sw, product, width_fraction=width_fraction)

    force_single = eq_type == Equipment.EquipmentType.FRIDGE and not getattr(
        product, "is_stackable", True
    )
    return calculate_max_capacity_from_dimensions(
        sw,
        sh,
        sd,
        product,
        width_fraction=width_fraction,
        force_single_layer=force_single or eq_type == Equipment.EquipmentType.HANGER,
    )


def refresh_slot_max_capacity(slot: EquipmentSlot, product: Product | None = None) -> int:
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
