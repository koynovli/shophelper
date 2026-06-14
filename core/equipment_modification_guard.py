"""Проверки перед удалением оборудования или изменением его конфигурации полок/слотов."""

from __future__ import annotations

from dataclasses import dataclass, field

from rest_framework.exceptions import ValidationError

from .models import (
    Equipment,
    EquipmentSlot,
    Inventory,
    PlacementTask,
    Planogram,
    ShelfClearingTask,
)

ACTIVE_PLACEMENT_STATUSES = (
    PlacementTask.Status.CREATED,
    PlacementTask.Status.PENDING,
    PlacementTask.Status.IN_PROGRESS,
)

ACTIVE_CLEARING_STATUSES = (
    ShelfClearingTask.Status.CREATED,
    ShelfClearingTask.Status.PENDING,
    ShelfClearingTask.Status.IN_PROGRESS,
)

LAYOUT_CHANGE_BLOCKED_MSG = (
    "Нельзя изменить конфигурацию: на оборудовании есть товар или активные задачи. "
    "Сначала отмените задачи выкладки и уберите товар с полок "
    "(создайте задание на уборку на склад)."
)

EQUIPMENT_DELETE_BLOCKED_MSG = (
    "Нельзя удалить оборудование: на нём есть товар или активные задачи. "
    "Сначала отмените задачи выкладки и уберите товар с полок "
    "(создайте задание на уборку на склад)."
)


@dataclass(frozen=True)
class OccupiedSlotInfo:
    slot_id: int
    row_index: int
    col_index: int
    product_id: int | None
    product_name: str | None
    current_qty: int
    has_clearing_task: bool
    planogram_id: int | None

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "current_qty": self.current_qty,
            "has_clearing_task": self.has_clearing_task,
            "planogram_id": self.planogram_id,
        }


@dataclass
class EquipmentModificationAssessment:
    can_modify_layout: bool
    can_delete: bool
    blockers: list[str] = field(default_factory=list)
    occupied_slots: list[OccupiedSlotInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "can_modify_layout": self.can_modify_layout,
            "can_delete": self.can_delete,
            "blockers": self.blockers,
            "occupied_slots": [s.to_dict() for s in self.occupied_slots],
        }


def _occupied_slots(equipment: Equipment) -> list[OccupiedSlotInfo]:
    clearing_planogram_ids = set(
        ShelfClearingTask.objects.filter(
            equipment=equipment,
            status__in=ACTIVE_CLEARING_STATUSES,
            planogram_id__isnull=False,
        ).values_list("planogram_id", flat=True)
    )
    rows: list[OccupiedSlotInfo] = []
    slots = (
        EquipmentSlot.objects.filter(equipment=equipment, current_qty__gt=0)
        .prefetch_related("planograms__product")
        .order_by("row_index", "col_index")
    )
    for slot in slots:
        pg = slot.planograms.first()
        rows.append(
            OccupiedSlotInfo(
                slot_id=slot.pk,
                row_index=slot.row_index,
                col_index=slot.col_index,
                product_id=pg.product_id if pg else None,
                product_name=pg.product.name if pg else None,
                current_qty=int(slot.current_qty),
                has_clearing_task=pg.pk in clearing_planogram_ids if pg else False,
                planogram_id=pg.pk if pg else None,
            )
        )
    return rows


def assess_equipment_modification(equipment: Equipment) -> EquipmentModificationAssessment:
    blockers: list[str] = []
    occupied = _occupied_slots(equipment)

    if occupied:
        blockers.append(
            f"товар на {len(occupied)} "
            f"{'слоте' if len(occupied) == 1 else 'слотах'}"
        )

    shelf_inv_count = Inventory.objects.filter(
        shelf__equipment=equipment,
        status=Inventory.LocationStatus.SHELF,
        quantity__gt=0,
    ).count()
    if shelf_inv_count:
        blockers.append(f"остатки на полках ({shelf_inv_count} записей)")

    placement_count = PlacementTask.objects.filter(
        equipment=equipment,
        status__in=ACTIVE_PLACEMENT_STATUSES,
    ).count()
    if placement_count:
        blockers.append(
            f"активные задачи выкладки ({placement_count})"
        )

    clearing_count = ShelfClearingTask.objects.filter(
        equipment=equipment,
        status__in=ACTIVE_CLEARING_STATUSES,
    ).count()
    if clearing_count:
        blockers.append(
            f"активные задачи уборки на склад ({clearing_count})"
        )

    blocked = len(blockers) > 0
    return EquipmentModificationAssessment(
        can_modify_layout=not blocked,
        can_delete=not blocked,
        blockers=blockers,
        occupied_slots=occupied,
    )


def equipment_has_blocking_stock_or_tasks(equipment: Equipment) -> bool:
    return not assess_equipment_modification(equipment).can_modify_layout


def _block_message(prefix: str, blockers: list[str]) -> str:
    if not blockers:
        return prefix
    return f"{prefix} Есть: {', '.join(blockers)}."


def ensure_equipment_layout_can_change(equipment: Equipment) -> None:
    assessment = assess_equipment_modification(equipment)
    if not assessment.can_modify_layout:
        raise ValidationError(
            {"detail": _block_message(LAYOUT_CHANGE_BLOCKED_MSG, assessment.blockers)}
        )


def ensure_equipment_can_be_deleted(equipment: Equipment) -> None:
    assessment = assess_equipment_modification(equipment)
    if not assessment.can_delete:
        raise ValidationError(
            {"detail": _block_message(EQUIPMENT_DELETE_BLOCKED_MSG, assessment.blockers)}
        )


PLANOGRAM_DELETE_BLOCKED_MSG = (
    "Нельзя удалить позицию планограммы: на слоте есть товар или активные задачи. "
    "Сначала отмените задачи выкладки и уберите товар с полки."
)


@dataclass(frozen=True)
class PlanogramDeleteAssessment:
    can_delete: bool
    blockers: list[str]

    def to_dict(self) -> dict:
        return {
            "can_delete": self.can_delete,
            "blockers": self.blockers,
        }


def assess_planogram_deletion(planogram: Planogram) -> PlanogramDeleteAssessment:
    blockers: list[str] = []
    slot = planogram.slot
    if int(slot.current_qty or 0) > 0:
        blockers.append(f"на слоте {int(slot.current_qty)} шт. товара")

    placement_count = PlacementTask.objects.filter(
        planogram=planogram,
        status__in=ACTIVE_PLACEMENT_STATUSES,
    ).count()
    if placement_count:
        blockers.append(f"активные задачи выкладки ({placement_count})")

    clearing_count = ShelfClearingTask.objects.filter(
        planogram=planogram,
        status__in=ACTIVE_CLEARING_STATUSES,
    ).count()
    if clearing_count:
        blockers.append(f"активные задачи уборки ({clearing_count})")

    return PlanogramDeleteAssessment(
        can_delete=len(blockers) == 0,
        blockers=blockers,
    )


def ensure_planogram_can_be_deleted(planogram: Planogram) -> None:
    assessment = assess_planogram_deletion(planogram)
    if not assessment.can_delete:
        raise ValidationError(
            {
                "detail": _block_message(
                    PLANOGRAM_DELETE_BLOCKED_MSG,
                    assessment.blockers,
                )
            }
        )
