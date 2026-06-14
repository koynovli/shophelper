"""Проверки перед удалением номенклатуры (Product)."""

from __future__ import annotations

from dataclasses import dataclass

from rest_framework.exceptions import ValidationError

from .models import (
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    StockItem,
)

ACTIVE_PLACEMENT_STATUSES = (
    PlacementTask.Status.CREATED,
    PlacementTask.Status.PENDING,
    PlacementTask.Status.IN_PROGRESS,
)

HISTORICAL_PLACEMENT_STATUSES = (
    PlacementTask.Status.COMPLETED,
    PlacementTask.Status.FAILED,
)


@dataclass(frozen=True)
class ProductDeleteAssessment:
    can_delete: bool
    blockers: list[str]
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "can_delete": self.can_delete,
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


def assess_product_deletion(product: Product) -> ProductDeleteAssessment:
    blockers: list[str] = []

    if Planogram.objects.filter(product=product).exists():
        blockers.append("планограммы")
    if ProductBatch.objects.filter(product=product, current_quantity__gt=0).exists():
        blockers.append("партии с остатком")
    if PlacementTask.objects.filter(
        product=product,
        status__in=ACTIVE_PLACEMENT_STATUSES,
    ).exists():
        blockers.append("активные задачи выкладки")
    if (
        ProductBatch.objects.filter(product=product).exists()
        and StockItem.objects.filter(product=product, quantity__gt=0).exists()
    ):
        blockers.append("остаток на складе")

    warnings: list[str] = []
    historical_count = PlacementTask.objects.filter(
        product=product,
        status__in=HISTORICAL_PLACEMENT_STATUSES,
    ).count()
    if historical_count:
        warnings.append(
            f"Есть {historical_count} завершённых или проблемных задач выкладки по этому товару."
        )

    return ProductDeleteAssessment(
        can_delete=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
    )


def product_delete_block_message(blockers: list[str]) -> str:
    return f"Нельзя удалить: есть {', '.join(blockers)}."


def ensure_product_can_be_deleted(product: Product) -> None:
    assessment = assess_product_deletion(product)
    if not assessment.can_delete:
        raise ValidationError({"detail": product_delete_block_message(assessment.blockers)})
