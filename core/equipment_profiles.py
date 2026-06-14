"""Профили типов оборудования: слоты, layout, полки."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Equipment

LayoutMode = str  # grid | linear | single | expo_vertical

MANNEQUIN_ZONE_LABELS = ("Верх", "Низ", "Аксессуар")


@dataclass(frozen=True)
class SlotSpec:
    row_index: int
    col_index: int
    width_percent: float
    slot_label: str = ""


@dataclass(frozen=True)
class EquipmentProfile:
    layout_mode: LayoutMode
    needs_shelves: bool
    default_rows_count: int
    cols_per_row: int = 4
    col_width_percent: float = 25.0
    max_hanger_rows: int = 2
    mannequin_zones: int = 3


PROFILES: dict[str, EquipmentProfile] = {
    Equipment.EquipmentType.SHELF: EquipmentProfile(
        layout_mode="grid",
        needs_shelves=True,
        default_rows_count=4,
    ),
    Equipment.EquipmentType.FRIDGE: EquipmentProfile(
        layout_mode="grid",
        needs_shelves=True,
        default_rows_count=4,
    ),
    Equipment.EquipmentType.HANGER: EquipmentProfile(
        layout_mode="linear",
        needs_shelves=True,
        default_rows_count=2,
        max_hanger_rows=2,
    ),
    Equipment.EquipmentType.BOX: EquipmentProfile(
        layout_mode="single",
        needs_shelves=True,
        default_rows_count=1,
    ),
    Equipment.EquipmentType.MANNEQUIN: EquipmentProfile(
        layout_mode="expo_vertical",
        needs_shelves=False,
        default_rows_count=3,
        mannequin_zones=3,
    ),
}

LEGACY_TYPE_MAP = {
    "shelving": Equipment.EquipmentType.SHELF,
    "pegboard": Equipment.EquipmentType.HANGER,
    "pallet": Equipment.EquipmentType.BOX,
    "display": Equipment.EquipmentType.MANNEQUIN,
}


def normalize_equipment_type(eq_type: str) -> str:
    raw = str(eq_type or Equipment.EquipmentType.SHELF)
    return LEGACY_TYPE_MAP.get(raw, raw)


def get_profile(eq_type: str) -> EquipmentProfile:
    normalized = normalize_equipment_type(eq_type)
    return PROFILES.get(normalized, PROFILES[Equipment.EquipmentType.SHELF])


def layout_mode(eq_type: str) -> LayoutMode:
    return get_profile(eq_type).layout_mode


def needs_shelves(eq_type: str) -> bool:
    return get_profile(eq_type).needs_shelves


def default_rows_count(eq_type: str) -> int:
    return get_profile(eq_type).default_rows_count


MAX_SLOTS_PER_ROW = 8


def _grid_specs_from_custom_layouts(equipment: Equipment, rows: int) -> list[SlotSpec] | None:
    """Слоты из Equipment.row_slot_layouts; None — если разбивка не задана/невалидна."""
    layouts = getattr(equipment, "row_slot_layouts", None)
    if not layouts or not isinstance(layouts, list):
        return None

    specs: list[SlotSpec] = []
    for r in range(rows):
        row_cfg = layouts[r] if r < len(layouts) else None
        if not isinstance(row_cfg, dict):
            count = 1
            widths = [100.0]
        else:
            count = int(row_cfg.get("slot_count") or 0)
            count = max(1, min(count, MAX_SLOTS_PER_ROW))
            raw_widths = row_cfg.get("widths") or []
            widths = [float(w) for w in raw_widths if isinstance(w, (int, float))]
            if len(widths) != count or sum(widths) <= 0:
                widths = [round(100.0 / count, 4)] * count
        for c in range(count):
            specs.append(
                SlotSpec(
                    row_index=r,
                    col_index=c,
                    width_percent=widths[c],
                )
            )
    return specs


def validate_row_slot_layouts(layouts, rows_count: int) -> str | None:
    """Возвращает текст ошибки или None. Пустой список допустим (стандартная сетка)."""
    if layouts in (None, []):
        return None
    if not isinstance(layouts, list):
        return "Разбивка рядов должна быть списком."
    if rows_count and len(layouts) != int(rows_count):
        return "Число строк разбивки должно совпадать с числом рядов."
    for idx, row_cfg in enumerate(layouts):
        if not isinstance(row_cfg, dict):
            return f"Ряд {idx + 1}: ожидается объект с slot_count и widths."
        count = int(row_cfg.get("slot_count") or 0)
        if count < 1 or count > MAX_SLOTS_PER_ROW:
            return f"Ряд {idx + 1}: число слотов 1–{MAX_SLOTS_PER_ROW}."
        widths = row_cfg.get("widths") or []
        if not isinstance(widths, list) or len(widths) != count:
            return f"Ряд {idx + 1}: число значений ширины должно равняться числу слотов."
        if not all(isinstance(w, (int, float)) and w > 0 for w in widths):
            return f"Ряд {idx + 1}: ширины должны быть положительными числами."
        if abs(sum(widths) - 100.0) > 1.0:
            return f"Ряд {idx + 1}: сумма ширин должна быть 100%."
    return None


def default_slots_spec(equipment: Equipment) -> list[SlotSpec]:
    profile = get_profile(equipment.type)
    rows = int(equipment.rows_count or 0) or profile.default_rows_count

    if profile.layout_mode == "grid":
        rows = max(rows, 1)
        custom = _grid_specs_from_custom_layouts(equipment, rows)
        if custom is not None:
            return custom
        specs: list[SlotSpec] = []
        for r in range(rows):
            for c in range(profile.cols_per_row):
                specs.append(
                    SlotSpec(
                        row_index=r,
                        col_index=c,
                        width_percent=profile.col_width_percent,
                    )
                )
        return specs

    if profile.layout_mode == "linear":
        row_count = min(max(rows, 1), profile.max_hanger_rows)
        return [
            SlotSpec(row_index=r, col_index=0, width_percent=100.0)
            for r in range(row_count)
        ]

    if profile.layout_mode == "single":
        return [SlotSpec(row_index=0, col_index=0, width_percent=100.0)]

    if profile.layout_mode == "expo_vertical":
        labels = MANNEQUIN_ZONE_LABELS[: profile.mannequin_zones]
        return [
            SlotSpec(
                row_index=i,
                col_index=0,
                width_percent=100.0,
                slot_label=labels[i] if i < len(labels) else "",
            )
            for i in range(profile.mannequin_zones)
        ]

    return [SlotSpec(row_index=0, col_index=0, width_percent=100.0)]


def shelf_dimensions_for_equipment(equipment: Equipment, level: int) -> dict:
    """Габариты полки из габаритов оборудования (см)."""
    w = float(equipment.width or 100)
    d = float(equipment.height or 60)
    profile = get_profile(equipment.type)
    total_rows = max(int(equipment.rows_count or 0), profile.default_rows_count, 1)

    if profile.layout_mode == "linear":
        return {"width": w, "height": 8.0, "depth": d}
    if profile.layout_mode == "single":
        return {"width": w, "height": float(equipment.width or 60), "depth": d}
    if profile.layout_mode == "expo_vertical":
        return {"width": w, "height": d / 3, "depth": d}

    h = max(d / total_rows, 10.0)
    return {"width": w, "height": h, "depth": d}


def virtual_shelf_dimensions_for_slot(slot, equipment: Equipment) -> dict | None:
    """Виртуальные габариты для mannequin (без Shelf в БД)."""
    profile = get_profile(equipment.type)
    if profile.layout_mode != "expo_vertical":
        return None
    w = float(equipment.width or 100)
    d = float(equipment.height or 60)
    zone_h = max(d / profile.mannequin_zones, 10.0)
    return {"width": w, "height": zone_h, "depth": d}
