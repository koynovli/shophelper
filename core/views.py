from datetime import date

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Inventory, ProductBatch, SupplyOrder, SupplyOrderItem
from .serializers import ProductBatchSerializer, SupplyOrderSerializer


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
        "created_by",
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
                    '[{"item_id": ..., "expiration_date": "YYYY-MM-DD"}, ...].'
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

                    batch = ProductBatch.objects.create(
                        product=item.product,
                        store=order.store,
                        supply_item=item,
                        purchase_price=item.price_per_unit,
                        initial_quantity=item.quantity,
                        current_quantity=item.quantity,
                        manufacture_date=None,
                        expiration_date=exp_date,
                        is_active=True,
                    )
                    Inventory.objects.update_or_create(
                        store=order.store,
                        product=item.product,
                        batch=batch,
                        defaults={
                            "quantity": item.quantity,
                            "status": Inventory.LocationStatus.WAREHOUSE,
                        },
                    )

                order.status = SupplyOrder.Status.RECEIVED
                order.received_at = timezone.now()
                order.save(update_fields=["status", "received_at"])
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
