from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from .models import Product

FAR_FUTURE_EXPIRY = date(2099, 12, 31)


def product_tracks_expiry(product: Product) -> bool:
    return product.shelf_life_days is not None and int(product.shelf_life_days) > 0


def expiration_from_manufacture(product: Product, manufacture_date: date) -> date:
    days = int(product.shelf_life_days or 0)
    if days < 1:
        raise ValueError("shelf_life_days must be positive for expiry calculation.")
    return manufacture_date + timedelta(days=days)


def batch_dates_for_receiving(
    product: Product,
    manufacture_date: date | None,
) -> tuple[date | None, date]:
    """Возвращает (manufacture_date, expiration_date) для новой партии при приёмке."""
    if product_tracks_expiry(product):
        if manufacture_date is None:
            raise ValueError("manufacture_date is required for this product.")
        today = timezone.localdate()
        if manufacture_date > today:
            raise ValueError("manufacture_date cannot be in the future.")
        return manufacture_date, expiration_from_manufacture(product, manufacture_date)
    return None, FAR_FUTURE_EXPIRY
