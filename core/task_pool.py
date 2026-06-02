from __future__ import annotations

from django.db.models import Q

from .models import PlacementTask, StaffTask, User


def _placement_title(task: PlacementTask) -> str:
    return f"Выложить: {task.product.name} — {task.quantity} шт."


def _placement_destination(task: PlacementTask) -> str:
    if task.planogram_id and task.planogram.slot_id:
        slot = task.planogram.slot
        return (
            f"{task.equipment.name} → Полка {slot.row_index + 1} → "
            f"Ячейка {slot.col_index + 1}"
        )
    return task.equipment.name


def _placement_to_dto(task: PlacementTask) -> dict:
    assigned = None
    if task.assigned_to_id:
        assigned = {
            "id": task.assigned_to_id,
            "username": task.assigned_to.username,
        }
    return {
        "task_type": "placement",
        "id": str(task.pk),
        "title": _placement_title(task),
        "status": task.status,
        "assigned_to": assigned,
        "destination": _placement_destination(task),
        "product": {
            "id": task.product_id,
            "name": task.product.name,
            "sku": task.product.sku,
        },
        "equipment": {"id": task.equipment_id, "name": task.equipment.name},
        "quantity": task.quantity,
        "slot_verified": task.slot_verified_at is not None,
        "photo_url": task.photo_url,
        "has_chat": True,
        "created_at": task.created_at.isoformat(),
    }


def _staff_to_dto(task: StaffTask) -> dict:
    assigned = None
    if task.assigned_to_id:
        assigned = {
            "id": task.assigned_to_id,
            "username": task.assigned_to.username,
        }
    zone_name = task.zone.name if task.zone_id else None
    return {
        "task_type": "staff",
        "id": str(task.pk),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assigned_to": assigned,
        "zone": zone_name,
        "equipment": (
            {"id": task.equipment_id, "name": task.equipment.name}
            if task.equipment_id
            else None
        ),
        "requires_photo": task.requires_photo,
        "photo_url": task.photo_url,
        "has_chat": True,
        "created_at": task.created_at.isoformat(),
    }


def _normalize_status_filter(status: str | None) -> tuple[str | None, str | None]:
    """Маппинг общего фильтра UI на статусы placement/staff."""
    if not status or status == "ALL":
        return None, None
    if status in ("PENDING", "CREATED"):
        return PlacementTask.Status.CREATED, StaffTask.Status.CREATED
    if status == "IN_PROGRESS":
        return PlacementTask.Status.IN_PROGRESS, StaffTask.Status.IN_PROGRESS
    if status == "COMPLETED":
        return PlacementTask.Status.COMPLETED, StaffTask.Status.COMPLETED
    if status == "CANCELLED":
        return PlacementTask.Status.CANCELLED, StaffTask.Status.CANCELLED
    return status, status


def fetch_task_pool(
    *,
    status: str | None = None,
    task_type: str | None = None,
    assigned_to_id: int | None = None,
    user: User | None = None,
) -> list[dict]:
    """Объединённый список задач для UI управляющего и сотрудника."""
    items: list[dict] = []
    placement_status, staff_status = _normalize_status_filter(status)

    include_placement = task_type in (None, "placement", "all")
    include_staff = task_type in (None, "staff", "all")

    if include_placement:
        pt_qs = PlacementTask.objects.select_related(
            "product",
            "equipment",
            "planogram",
            "planogram__slot",
            "assigned_to",
        )
        if placement_status:
            pt_qs = pt_qs.filter(status=placement_status)
        if assigned_to_id is not None:
            pt_qs = pt_qs.filter(
                Q(assigned_to_id=assigned_to_id) | Q(assigned_to__isnull=True)
            )
        elif user and getattr(user, "role", None) == User.Role.EMPLOYEE:
            pt_qs = pt_qs.filter(
                Q(assigned_to_id=user.pk) | Q(assigned_to__isnull=True),
                status__in=(
                    PlacementTask.Status.CREATED,
                    PlacementTask.Status.PENDING,
                    PlacementTask.Status.IN_PROGRESS,
                ),
            )
        items.extend(_placement_to_dto(t) for t in pt_qs)

    if include_staff:
        st_qs = StaffTask.objects.select_related(
            "zone",
            "equipment",
            "assigned_to",
        )
        if staff_status:
            st_qs = st_qs.filter(status=staff_status)
        if assigned_to_id is not None:
            st_qs = st_qs.filter(
                Q(assigned_to_id=assigned_to_id) | Q(assigned_to__isnull=True)
            )
        elif user and getattr(user, "role", None) == User.Role.EMPLOYEE:
            st_qs = st_qs.filter(
                Q(assigned_to_id=user.pk) | Q(assigned_to__isnull=True),
                status__in=(
                    StaffTask.Status.CREATED,
                    StaffTask.Status.IN_PROGRESS,
                ),
            )
        items.extend(_staff_to_dto(t) for t in st_qs)

    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items
