from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Product

GRAMS_PER_KG = 1000
_KG_QUANT = Decimal("0.001")
WEIGHT_BULK_FILL_FRACTION = 0.55
MAX_BOX_PLANOGRAM_TARGET_KG = Decimal("100")


def compute_bulk_density_kg_m3(
    width_mm: float | None,
    height_mm: float | None,
    depth_mm: float | None,
    weight_g: float | None,
) -> float | None:
    """Насыпная плотность (кг/м³) из габаритов одной единицы (мм) и её массы (г)."""
    if width_mm is None or height_mm is None or depth_mm is None or weight_g is None:
        return None
    w, h, d, weight = float(width_mm), float(height_mm), float(depth_mm), float(weight_g)
    if w <= 0 or h <= 0 or d <= 0 or weight <= 0:
        return None
    vol_m3 = (w / 1000.0) * (h / 1000.0) * (d / 1000.0)
    if vol_m3 <= 0:
        return None
    particle_density = (weight / 1000.0) / vol_m3
    return round(particle_density * WEIGHT_BULK_FILL_FRACTION, 1)


def product_bulk_density_kg_m3(product: Product | None) -> float | None:
    if product is None:
        return None
    return compute_bulk_density_kg_m3(
        product.width,
        product.height,
        product.depth,
        product.weight,
    )


def product_stores_weight(product: Product | None) -> bool:
    if product is None:
        return False
    from .models import Product

    return getattr(product, "sale_unit", Product.SaleUnit.PIECE) == Product.SaleUnit.WEIGHT


def kg_to_grams(value: Decimal | str | float | int) -> int:
    """Конвертирует килограммы в целые граммы (округление HALF_UP)."""
    kg = Decimal(str(value))
    grams = (kg * GRAMS_PER_KG).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if grams < 0:
        raise ValueError("Вес не может быть отрицательным.")
    return int(grams)


def grams_to_kg(grams: int) -> Decimal:
    return (Decimal(int(grams)) * _KG_QUANT).quantize(Decimal("0.001"))


def format_quantity(product: Product | None, amount: int) -> str:
    """Форматирует количество с учётом единицы продажи товара."""
    qty = int(amount or 0)
    if product_stores_weight(product):
        return f"{grams_to_kg(qty)} кг"
    return f"{qty} шт."


def format_kg(grams: int) -> str:
    return f"{grams_to_kg(int(grams or 0))} кг"


def order_line_amount(
    product: Product | None,
    quantity_grams: int,
    purchase_price: Decimal,
) -> Decimal:
    """Сумма строки заказа: для веса — (г / 1000) × цена за кг, иначе шт × цена."""
    qty = int(quantity_grams or 0)
    if product_stores_weight(product):
        return (Decimal(qty) / Decimal(GRAMS_PER_KG)) * purchase_price
    return Decimal(qty) * purchase_price
