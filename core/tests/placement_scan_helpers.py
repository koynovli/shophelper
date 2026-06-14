from __future__ import annotations

from core.models import PlacementTask, PlacementTaskScan


def fulfill_placement_scan_requirements(
    task: PlacementTask,
    user,
    *,
    quantity: int | None = None,
) -> None:
    """Создаёт сканы для complete_placement_task в тестах."""
    qty = quantity if quantity is not None else int(task.quantity)
    for _ in range(qty):
        PlacementTaskScan.objects.create(
            task=task,
            product=task.product,
            batch=task.batch,
            scanned_by=user,
        )


def product_scan_payload(product) -> dict:
    return {"raw_code": product.sku}
