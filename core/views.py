from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Equipment, Inventory, ProductBatch, Shelf, SupplyOrder, SupplyOrderItem, Zone
from .serializers import (
    EquipmentSerializer,
    InventorySerializer,
    ProductBatchSerializer,
    ShelfSerializer,
    SupplyOrderSerializer,
    ZoneSerializer,
)


class ProductBatchFilter(filters.FilterSet):
    class Meta:
        model = ProductBatch
        fields = ("store", "product", "is_active")


class ProductBatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductBatch.objects.select_related(
        "product",
        "store",
        "supply_item",
        "supply_item__order",
    ).all()
    serializer_class = ProductBatchSerializer
    filterset_class = ProductBatchFilter

    @action(detail=False, methods=["get"], url_path="get-fefo")
    def get_fefo(self, request):
        product_id = request.query_params.get("product_id")
        if not product_id:
            return Response(
                {"detail": "Укажите query-параметр product_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        batch = (
            ProductBatch.objects.filter(
                product_id=product_id,
                expiration_date__gte=timezone.now().date(),
            )
            .order_by("expiration_date")
            .first()
        )
        if batch is None:
            return Response(
                {"detail": "Непросроченная партия для данного товара не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(batch)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SupplyOrderViewSet(viewsets.ModelViewSet):
    queryset = SupplyOrder.objects.prefetch_related("items").select_related(
        "company",
        "store",
        "supplier",
        "created_by",
        "received_by",
    )
    serializer_class = SupplyOrderSerializer

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        self.get_object()
        batches_payload = request.data.get("batches")
        if not isinstance(batches_payload, list) or len(batches_payload) == 0:
            return Response(
                {
                    "detail": "Ожидается непустой массив batches: "
                    '[{"item_id": ..., "expiration_date": "YYYY-MM-DD", '
                    '"actual_quantity": <опционально>}, ...].'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                order = SupplyOrder.objects.select_for_update().get(pk=self.kwargs["pk"])
                if order.status == SupplyOrder.Status.RECEIVED:
                    return Response(
                        {"detail": "Заказ уже принят."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                total_cost = Decimal("0")

                for entry in batches_payload:
                    if not isinstance(entry, dict):
                        raise ValueError("Каждый элемент batches должен быть объектом.")
                    item_id = entry.get("item_id")
                    exp_raw = entry.get("expiration_date")
                    if item_id is None or exp_raw is None:
                        raise ValueError(
                            "Для каждой партии нужны поля item_id и expiration_date."
                        )
                    exp_date = _parse_expiration_date(exp_raw)
                    if exp_date is None:
                        raise ValueError(
                            "Некорректная дата expiration_date (ожидается YYYY-MM-DD)."
                        )

                    try:
                        item = SupplyOrderItem.objects.select_for_update().get(
                            pk=item_id,
                            order=order,
                        )
                    except SupplyOrderItem.DoesNotExist as exc:
                        raise ValueError(
                            f"Позиция заказа id={item_id} не найдена или не относится "
                            "к этому заказу."
                        ) from exc

                    raw_actual = entry.get("actual_quantity", None)
                    if raw_actual is None:
                        actual_qty = item.quantity
                    else:
                        try:
                            actual_qty = int(raw_actual)
                        except (TypeError, ValueError) as exc:
                            raise ValueError(
                                "Поле actual_quantity должно быть целым числом."
                            ) from exc
                    if actual_qty < 0:
                        raise ValueError("actual_quantity не может быть отрицательным.")

                    item.actual_quantity = actual_qty
                    item.save(update_fields=["actual_quantity"])

                    line_cost = Decimal(actual_qty) * item.purchase_price
                    total_cost += line_cost

                    if actual_qty == 0:
                        continue

                    batch = ProductBatch.objects.create(
                        product=item.product,
                        store=order.store,
                        supply_item=item,
                        purchase_price=item.purchase_price,
                        initial_quantity=actual_qty,
                        current_quantity=actual_qty,
                        manufacture_date=None,
                        expiration_date=exp_date,
                        is_active=True,
                    )
                    Inventory.objects.update_or_create(
                        store=order.store,
                        product=item.product,
                        batch=batch,
                        defaults={
                            "quantity": actual_qty,
                            "status": Inventory.LocationStatus.WAREHOUSE,
                        },
                    )

                order.status = SupplyOrder.Status.RECEIVED
                order.received_at = timezone.now()
                order.total_cost = total_cost
                order.received_by = (
                    request.user if request.user.is_authenticated else None
                )
                order.save(
                    update_fields=[
                        "status",
                        "received_at",
                        "total_cost",
                        "received_by",
                    ]
                )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        order = self.get_object()
        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)


def _parse_expiration_date(raw):
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return parse_date(raw)
    return None


class ZoneFilter(filters.FilterSet):
    class Meta:
        model = Zone
        fields = ("store",)


class EquipmentFilter(filters.FilterSet):
    zone_id = filters.NumberFilter(field_name="zone_id")

    class Meta:
        model = Equipment
        fields = ("zone_id",)


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.select_related("store").prefetch_related(
        "equipment__shelves",
    )
    serializer_class = ZoneSerializer
    filterset_class = ZoneFilter


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.select_related("zone", "zone__store").prefetch_related(
        "shelves",
    )
    serializer_class = EquipmentSerializer
    filterset_class = EquipmentFilter


class ShelfViewSet(viewsets.ModelViewSet):
    queryset = Shelf.objects.select_related("equipment", "equipment__zone")
    serializer_class = ShelfSerializer


class InventoryViewSet(viewsets.ModelViewSet):
    queryset = Inventory.objects.select_related(
        "store",
        "product",
        "batch",
        "shelf",
        "shelf__equipment",
    )
    serializer_class = InventorySerializer

    @action(detail=False, methods=["get"])
    def shelf_fill_report(self, request):
        """
        Отчёт по заполненности полок.

        Для каждой полки суммируется фактический остаток (Inventory.quantity).
        Опорная «макс. вместимость» берётся как максимум из calculate_max_capacity
        по строкам остатков на этой полке — это верхняя оценка числа мест под один
        тип SKU в упрощённой 3D-решётке; при нескольких разных товарах показатель
        ориентировочный (дипломная модель без учёта смешанной укладки).
        """
        shelves = Shelf.objects.select_related(
            "equipment",
            "equipment__zone",
        ).order_by("equipment_id", "level")

        report = []
        for shelf in shelves:
            inv_qs = Inventory.objects.filter(shelf=shelf).select_related("product")
            current_total = sum(inv.quantity for inv in inv_qs)

            caps_positive = []
            for inv in inv_qs:
                cap = shelf.calculate_max_capacity(inv.product)
                if cap > 0:
                    caps_positive.append(cap)

            max_reference = max(caps_positive) if caps_positive else 0

            if max_reference > 0:
                fill_percent = min(
                    100.0,
                    round(current_total / max_reference * 100, 2),
                )
            else:
                fill_percent = None

            report.append(
                {
                    "shelf_id": shelf.pk,
                    "level": shelf.level,
                    "equipment_id": shelf.equipment_id,
                    "equipment_name": shelf.equipment.name,
                    "equipment_type": shelf.equipment.type,
                    "zone_id": shelf.equipment.zone_id,
                    "zone_name": shelf.equipment.zone.name,
                    "current_quantity_total": current_total,
                    "max_capacity_reference": max_reference,
                    "fill_percent": fill_percent,
                }
            )

        return Response(report, status=status.HTTP_200_OK)
