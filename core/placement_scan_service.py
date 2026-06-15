from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import PlacementTask, PlacementTaskScan, Product, User
from .product_units import (
    format_kg,
    format_quantity,
    kg_to_grams,
    product_stores_weight,
    weight_sufficient_threshold_grams,
    weight_task_scans_sufficient,
)
from .scan_service import ScanResolveResult, resolve_scan

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class PlacementScanError(Exception):
    pass


ACTIVE_PLACEMENT_STATUSES = (
    PlacementTask.Status.CREATED,
    PlacementTask.Status.PENDING,
    PlacementTask.Status.IN_PROGRESS,
)


def scanned_amount_for_task(task: PlacementTask) -> int:
    if product_stores_weight(task.product):
        total = task.scans.aggregate(total=Sum("weight_grams"))["total"]
        return int(total or 0)
    return task.scans.count()


def _placement_qs_for_user(user: AbstractUser, store_id: int | None):
    qs = PlacementTask.objects.filter(
        status__in=ACTIVE_PLACEMENT_STATUSES,
    ).select_related(
        "product",
        "equipment",
        "planogram",
        "planogram__slot",
        "batch",
        "assigned_to",
    )
    if store_id is not None:
        qs = qs.filter(equipment__zone__store_id=store_id)
    role = getattr(user, "role", None)
    if role == User.Role.EMPLOYEE:
        qs = qs.filter(Q(assigned_to_id=user.pk) | Q(assigned_to__isnull=True))
    return qs.order_by("product__name", "created_at", "pk").prefetch_related("scans")


def format_task_destination(task: PlacementTask) -> str:
    from .models import Equipment

    if task.planogram_id and task.planogram.slot_id:
        slot = task.planogram.slot
        if task.equipment.type == Equipment.EquipmentType.BOX:
            return f"{task.equipment.name} → Бокс / корзина"
        return (
            f"{task.equipment.name} → Полка {slot.row_index + 1} → "
            f"Ячейка {slot.col_index + 1}"
        )
    return task.equipment.name


def _task_destination(task: PlacementTask) -> str:
    return format_task_destination(task)


def _task_to_brief(task: PlacementTask) -> dict:
    batch_expiration = None
    if task.batch_id and task.batch:
        batch_expiration = task.batch.expiration_date.isoformat()
    required = int(task.quantity)
    done = scanned_amount_for_task(task)
    return {
        "id": task.pk,
        "quantity": required,
        "quantity_display": format_quantity(task.product, required),
        "sale_unit": task.product.sale_unit,
        "status": task.status,
        "destination": _task_destination(task),
        "equipment": {"id": task.equipment_id, "name": task.equipment.name},
        "slot_info": (
            {
                "id": task.planogram.slot_id,
                "row_index": task.planogram.slot.row_index,
                "col_index": task.planogram.slot.col_index,
            }
            if task.planogram_id and task.planogram.slot_id
            else None
        ),
        "batch_expiration": batch_expiration,
        "scans_done": done,
        "scans_required": required,
        "scans_done_display": format_quantity(task.product, done),
        "scans_required_display": format_quantity(task.product, required),
    }


def get_picking_list(user: AbstractUser, store_id: int | None) -> list[dict]:
    """Список товаров для сбора на складе, сгруппированный по product_id."""
    tasks = list(_placement_qs_for_user(user, store_id))
    groups: dict[int, dict] = {}
    for task in tasks:
        pid = task.product_id
        if pid not in groups:
            groups[pid] = {
                "product": {
                    "id": task.product_id,
                    "name": task.product.name,
                    "sku": task.product.sku,
                    "gtin": task.product.gtin,
                    "is_marked": task.product.is_marked,
                    "sale_unit": task.product.sale_unit,
                },
                "total_qty": 0,
                "total_qty_display": "",
                "tasks": [],
            }
        groups[pid]["total_qty"] += int(task.quantity)
        groups[pid]["tasks"].append(_task_to_brief(task))
    result = []
    for group in groups.values():
        product = Product.objects.filter(pk=group["product"]["id"]).first()
        group["total_qty_display"] = format_quantity(product, group["total_qty"])
        result.append(group)
    return sorted(result, key=lambda g: g["product"]["name"])


def scan_check_for_picking(
    user: AbstractUser,
    *,
    raw_code: str,
    store_id: int | None,
) -> dict:
    """Проверка: нужен ли отсканированный товар для текущих задач выкладки."""
    resolved = resolve_scan(raw_code, store_id)
    if resolved.product is None:
        return {
            "matches_picking": False,
            "message": resolved.message,
            "product": None,
            "suggested_tasks": [],
            "resolve": resolved.to_dict(),
        }

    tasks = [
        t
        for t in _placement_qs_for_user(user, store_id)
        if t.product_id == resolved.product.pk
    ]
    if not tasks:
        return {
            "matches_picking": False,
            "message": f"«{resolved.product.name}» сейчас не нужен для выкладки — возьмите другой товар.",
            "product": {
                "id": resolved.product.pk,
                "name": resolved.product.name,
                "sku": resolved.product.sku,
                "is_marked": resolved.product.is_marked,
                "sale_unit": resolved.product.sale_unit,
            },
            "suggested_tasks": [],
            "resolve": resolved.to_dict(),
        }

    suggested = [_task_to_brief(t) for t in tasks]
    total = sum(int(t.quantity) for t in tasks)
    qty_label = format_quantity(resolved.product, total)
    return {
        "matches_picking": True,
        "message": f"Да, нужен для выкладки: {resolved.product.name} — {qty_label}.",
        "product": {
            "id": resolved.product.pk,
            "name": resolved.product.name,
            "sku": resolved.product.sku,
            "is_marked": resolved.product.is_marked,
            "sale_unit": resolved.product.sale_unit,
        },
        "suggested_tasks": suggested,
        "resolve": resolved.to_dict(),
    }


def find_best_task_for_scan(
    user: AbstractUser,
    *,
    raw_code: str,
    store_id: int | None,
) -> dict:
    """Быстрая выкладка: скан товара → лучшая открытая задача и куда выложить."""
    check = scan_check_for_picking(user, raw_code=raw_code, store_id=store_id)
    if not check["matches_picking"] or not check["suggested_tasks"]:
        return check

    in_progress = [
        t
        for t in _placement_qs_for_user(user, store_id)
        if t.product_id == check["product"]["id"]
        and t.status == PlacementTask.Status.IN_PROGRESS
        and t.assigned_to_id == user.pk
    ]
    if in_progress:
        best = in_progress[0]
    else:
        open_tasks = [
            t
            for t in _placement_qs_for_user(user, store_id)
            if t.product_id == check["product"]["id"]
        ]
        best = open_tasks[0]

    check["best_task"] = _task_to_brief(best)
    check["message"] = (
        f"Выложить «{check['product']['name']}» → {check['best_task']['destination']}"
    )
    return check


def scan_count_for_task(task: PlacementTask) -> int:
    return scanned_amount_for_task(task)


def record_placement_scan(
    task_id: int,
    user: AbstractUser,
    *,
    raw_code: str | None = None,
    store_id: int | None,
    weight_kg: Decimal | str | float | None = None,
) -> tuple[PlacementTask, ScanResolveResult]:
    with transaction.atomic():
        task = (
            PlacementTask.objects.select_for_update()
            .select_related("product", "planogram", "planogram__slot", "equipment")
            .get(pk=task_id)
        )
        if task.status != PlacementTask.Status.IN_PROGRESS:
            raise PlacementScanError("Сканировать можно только задачу IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise PlacementScanError("Задача назначена другому сотруднику.")

        if product_stores_weight(task.product):
            weight_grams: int | None = None
            resolved: ScanResolveResult | None = None
            code = (raw_code or "").strip()
            if code:
                resolved = resolve_scan(code, store_id)
                if resolved.product is None or resolved.product.pk != task.product_id:
                    raise PlacementScanError(
                        resolved.message
                        if resolved.product is None
                        else "Отсканирован другой товар — нужен "
                        f"«{task.product.name}»."
                    )
                if resolved.weight_grams:
                    weight_grams = int(resolved.weight_grams)
            if weight_grams is None and weight_kg is not None:
                weight_grams = kg_to_grams(weight_kg)
            if weight_grams is None or weight_grams <= 0:
                raise PlacementScanError(
                    "Укажите вес в килограммах или отсканируйте весовой штрихкод."
                )

            current = scanned_amount_for_task(task)
            required = int(task.quantity)
            if current + weight_grams > required:
                remaining = max(0, required - current)
                raise PlacementScanError(
                    f"Превышен план выкладки. Осталось: {format_kg(remaining)}."
                )

            batch = resolved.batch if resolved is not None else None
            if batch is None:
                from .scan_service import _active_batch_qs

                batch = _active_batch_qs(
                    product_id=task.product_id,
                    store_id=store_id or task.equipment.zone.store_id,
                ).first()

            PlacementTaskScan.objects.create(
                task=task,
                product=task.product,
                batch=batch,
                serial_number=None,
                scanned_by=user,
                weight_grams=weight_grams,
            )
            if resolved is None:
                resolved = ScanResolveResult(
                    status="found",
                    scan_kind="manual_weight",
                    product=task.product,
                    batch=batch,
                    message=f"Зафиксировано {format_kg(weight_grams)}.",
                    parsed={},
                    weight_grams=weight_grams,
                    sale_unit=task.product.sale_unit,
                )
        else:
            code = (raw_code or "").strip()
            if not code:
                raise PlacementScanError("Отсканируйте код товара.")
            resolved = resolve_scan(code, store_id)
            if resolved.product is None or resolved.product.pk != task.product_id:
                raise PlacementScanError(
                    resolved.message
                    if resolved.product is None
                    else "Отсканирован другой товар — нужен "
                    f"«{task.product.name}»."
                )

            current = scan_count_for_task(task)
            if current >= int(task.quantity):
                raise PlacementScanError("Уже отсканировано достаточно единиц для этой задачи.")

            if task.product.is_marked:
                if resolved.batch is None or not resolved.parsed.get("serial"):
                    raise PlacementScanError(
                        "Для маркированного товара отсканируйте Data Matrix с серийным номером."
                    )
                serial = resolved.parsed["serial"]
                if PlacementTaskScan.objects.filter(task=task, serial_number=serial).exists():
                    raise PlacementScanError("Эта единица уже отсканирована для задачи.")
                PlacementTaskScan.objects.create(
                    task=task,
                    product=task.product,
                    batch=resolved.batch,
                    serial_number=serial,
                    scanned_by=user,
                )
            else:
                PlacementTaskScan.objects.create(
                    task=task,
                    product=task.product,
                    batch=resolved.batch,
                    serial_number=None,
                    scanned_by=user,
                )

    task = PlacementTask.objects.select_related(
        "product", "equipment", "planogram", "planogram__slot", "batch"
    ).get(pk=task_id)
    return task, resolved


def ensure_placement_scans_complete(task: PlacementTask) -> None:
    required = int(task.quantity)
    if product_stores_weight(task.product):
        done = scanned_amount_for_task(task)
        if weight_task_scans_sufficient(done, required):
            return
        threshold = weight_sufficient_threshold_grams(required)
        raise PlacementScanError(
            f"Отсканируйте товар: {format_kg(done)} из {format_kg(threshold)} "
            f"(мин. 80% задачи {format_kg(required)})."
        )

    count = scan_count_for_task(task)
    if count < required:
        raise PlacementScanError(
            f"Отсканируйте товар: {count} из {required} единиц."
        )
    if task.product.is_marked:
        serials = task.scans.exclude(serial_number__isnull=True).values_list(
            "serial_number", flat=True
        )
        if len(set(serials)) < required:
            raise PlacementScanError(
                "Для маркированного товара нужен уникальный скан каждой единицы."
            )
