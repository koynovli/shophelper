from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from shophelper.utils import parse_data_matrix

from .models import Product, ProductBatch


@dataclass
class ScanResolveResult:
    status: str
    scan_kind: str
    product: Product | None
    batch: ProductBatch | None
    message: str
    parsed: dict[str, Any]

    def to_dict(self, *, product_serializer=None, batch_serializer=None) -> dict:
        product_data = None
        batch_data = None
        if self.product is not None and product_serializer is not None:
            product_data = product_serializer(self.product).data
        elif self.product is not None:
            product_data = {
                "id": self.product.pk,
                "name": self.product.name,
                "sku": self.product.sku,
                "gtin": self.product.gtin,
                "is_marked": self.product.is_marked,
            }
        if self.batch is not None and batch_serializer is not None:
            batch_data = batch_serializer(self.batch).data
        elif self.batch is not None:
            batch_data = {
                "id": self.batch.pk,
                "expiration_date": self.batch.expiration_date.isoformat(),
                "current_quantity": self.batch.current_quantity,
                "serial_number": self.batch.serial_number,
            }
        return {
            "status": self.status,
            "scan_kind": self.scan_kind,
            "message": self.message,
            "product": product_data,
            "batch": batch_data,
            "parsed": self.parsed,
        }


def _normalize_gtin(raw: str) -> str | None:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) < 8 or len(digits) > 14:
        return None
    return digits.zfill(14)


def _find_product_by_gtin(gtin: str) -> Product | None:
    normalized = _normalize_gtin(gtin)
    if normalized is None:
        return None
    product = Product.objects.filter(gtin=normalized).first()
    if product is not None:
        return product
    stripped = normalized.lstrip("0")
    if stripped:
        return Product.objects.filter(gtin=stripped.zfill(14)).first()
    return None


def _find_product_by_plain_code(code: str) -> Product | None:
    normalized = _normalize_gtin(code)
    if normalized:
        product = _find_product_by_gtin(normalized)
        if product is not None:
            return product
    sku = code.strip()
    if not sku:
        return None
    return Product.objects.filter(sku__iexact=sku).first()


def _active_batch_qs(*, product_id: int, store_id: int | None):
    today = timezone.localdate()
    qs = ProductBatch.objects.filter(
        product_id=product_id,
        is_active=True,
        current_quantity__gt=0,
        expiration_date__gte=today,
    )
    if store_id is not None:
        qs = qs.filter(store_id=store_id)
    return qs.order_by("expiration_date", "pk")


def _find_marked_batch(
    *,
    product_id: int,
    serial: str,
    store_id: int | None,
) -> ProductBatch | None:
    qs = ProductBatch.objects.filter(
        product_id=product_id,
        serial_number=serial,
        is_active=True,
        current_quantity__gt=0,
    )
    if store_id is not None:
        qs = qs.filter(store_id=store_id)
    return qs.first()


def resolve_scan(raw_code: str, store_id: int | None = None) -> ScanResolveResult:
    """Разбор кода маркировки / EAN / SKU и поиск товара (и партии для marked)."""
    parsed = parse_data_matrix(raw_code)
    gtin = parsed.get("gtin")
    serial = parsed.get("serial")

    if gtin:
        product = _find_product_by_gtin(gtin)
        if product is None:
            return ScanResolveResult(
                status="not_found",
                scan_kind="gtin",
                product=None,
                batch=None,
                message="Товар с таким GTIN не найден в каталоге.",
                parsed=parsed,
            )
        if product.is_marked:
            if not serial:
                return ScanResolveResult(
                    status="product_only",
                    scan_kind="marked_gtin",
                    product=product,
                    batch=None,
                    message="Отсканирован GTIN маркированного товара; нужен код единицы (Data Matrix).",
                    parsed=parsed,
                )
            batch = _find_marked_batch(
                product_id=product.pk, serial=serial, store_id=store_id
            )
            if batch is None:
                return ScanResolveResult(
                    status="not_found",
                    scan_kind="marked_unit",
                    product=product,
                    batch=None,
                    message="Единица с таким серийным номером не найдена на складе.",
                    parsed=parsed,
                )
            return ScanResolveResult(
                status="found",
                scan_kind="marked_unit",
                product=product,
                batch=batch,
                message="Маркированная единица найдена.",
                parsed=parsed,
            )
        batch = _active_batch_qs(product_id=product.pk, store_id=store_id).first()
        return ScanResolveResult(
            status="found" if batch else "product_only",
            scan_kind="gtin",
            product=product,
            batch=batch,
            message="Товар найден по GTIN."
            if batch
            else "Товар найден, но нет доступных партий на складе.",
            parsed=parsed,
        )

    plain = (raw_code or "").strip()
    product = _find_product_by_plain_code(plain)
    if product is None:
        return ScanResolveResult(
            status="not_found",
            scan_kind="unknown",
            product=None,
            batch=None,
            message="Код не распознан. Отсканируйте GTIN/EAN или Data Matrix.",
            parsed=parsed,
        )

    if product.is_marked:
        return ScanResolveResult(
            status="product_only",
            scan_kind="sku",
            product=product,
            batch=None,
            message="Для маркированного товара нужен код Data Matrix (с серийным номером).",
            parsed=parsed,
        )

    batch = _active_batch_qs(product_id=product.pk, store_id=store_id).first()
    return ScanResolveResult(
        status="found" if batch else "product_only",
        scan_kind="sku" if product.sku.lower() == plain.lower() else "ean",
        product=product,
        batch=batch,
        message="Товар найден."
        if batch
        else "Товар найден, но нет доступных партий на складе.",
        parsed=parsed,
    )


def validate_task_product_scan(
    *,
    task_product_id: int,
    raw_code: str,
    store_id: int | None,
    expected_batch_id: int | None = None,
) -> ScanResolveResult:
    """Проверка скана товара перед завершением задачи (списание, уборка)."""
    raw_code = (raw_code or "").strip()
    if not raw_code:
        raise ValueError("Отсканируйте код товара.")
    resolved = resolve_scan(raw_code, store_id)
    if resolved.product is None or resolved.product.pk != task_product_id:
        raise ValueError(
            resolved.message
            if resolved.product is None
            else "Отсканирован другой товар."
        )
    if resolved.product.is_marked:
        if resolved.batch is None:
            raise ValueError(
                "Для маркированного товара отсканируйте Data Matrix с серийным номером."
            )
        if expected_batch_id is not None and resolved.batch.pk != expected_batch_id:
            raise ValueError("Отсканирована другая партия / единица.")
    return resolved
