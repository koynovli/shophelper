import random
import uuid
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shophelper.utils import parse_data_matrix

from .models import (
    Category,
    Equipment,
    Inventory,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    StockItem,
    SupplyOrder,
    SupplyOrderItem,
    User,
    Zone,
)
from .permissions import IsRoleAdmin
from .serializers import (
    EquipmentSerializer,
    InventorySerializer,
    PlacementTaskAdminUpdateSerializer,
    PlanogramReadSerializer,
    PlanogramWriteSerializer,
    PlacementTaskReadSerializer,
    PlacementTaskUpdateSerializer,
    ProductBatchSerializer,
    ProductBriefSerializer,
    ProductSerializer,
    ShelfSerializer,
    StockItemSerializer,
    SupplyOrderSerializer,
    ZoneSerializer,
)


class ScanCodeView(APIView):
    """Сканирование маркировки: доступ без JWT (терминалы / внешние клиенты)."""

    permission_classes = [AllowAny]
    """
    Принимает сырую строку со сканера маркировки, парсит GS1 Data Matrix,
    ищет товар по GTIN и активную партию по серийному номеру (AI 21).
    """

    def post(self, request):
        raw_code = request.data.get("raw_code")
        if raw_code is None or not isinstance(raw_code, str):
            return Response(
                {"detail": "Ожидается поле raw_code (строка)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parsed = parse_data_matrix(raw_code)
        gtin = parsed.get("gtin")
        serial = parsed.get("serial")

        if not gtin:
            return Response(
                {"product": None, "batch": None, "status": "not_found"},
                status=status.HTTP_200_OK,
            )

        product = Product.objects.filter(gtin=gtin).select_related("category").first()
        if product is None:
            return Response(
                {"product": None, "batch": None, "status": "not_found"},
                status=status.HTTP_200_OK,
            )

        product_data = ProductSerializer(product).data

        if not serial:
            return Response(
                {"product": product_data, "batch": None, "status": "not_found"},
                status=status.HTTP_200_OK,
            )

        batch = (
            ProductBatch.objects.filter(
                product=product,
                serial_number=serial,
                is_active=True,
            )
            .select_related("product", "store", "supply_item")
            .first()
        )

        if batch is None:
            return Response(
                {"product": product_data, "batch": None, "status": "not_found"},
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "product": product_data,
                "batch": ProductBatchSerializer(batch).data,
                "status": "found",
            },
            status=status.HTTP_200_OK,
        )


class ProductBatchFilter(filters.FilterSet):
    class Meta:
        model = ProductBatch
        fields = ("store", "product", "is_active")


class ProductBatchViewSet(viewsets.ModelViewSet):
    queryset = ProductBatch.objects.select_related(
        "product",
        "store",
        "supply_item",
        "supply_item__order",
    ).all()
    serializer_class = ProductBatchSerializer
    filterset_class = ProductBatchFilter

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsRoleAdmin()]

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

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsRoleAdmin()]


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.select_related("zone", "zone__store").prefetch_related(
        "shelves",
        "slots",
        "slots__planograms",
        "slots__planograms__product",
    )
    serializer_class = EquipmentSerializer
    filterset_class = EquipmentFilter

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsRoleAdmin()]


class ShelfViewSet(viewsets.ModelViewSet):
    queryset = Shelf.objects.select_related("equipment", "equipment__zone")
    serializer_class = ShelfSerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsRoleAdmin()]


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


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Список товаров (планограмма, мерчандайзинг); create-test — только админ."""

    queryset = Product.objects.select_related("category").order_by("name")
    serializer_class = ProductBriefSerializer

    @action(detail=False, methods=["post"], url_path="create-test")
    def create_test(self, request):
        if getattr(request.user, "role", None) != User.Role.ADMIN:
            return Response(
                {"detail": "Создание тестового товара доступно только администратору."},
                status=status.HTTP_403_FORBIDDEN,
            )
        category, _ = Category.objects.get_or_create(name="Служебная категория (выкладка)")
        suffix = uuid.uuid4().hex[:10]
        sku = f"TEST-PL-{suffix}"
        product = Product.objects.create(
            name=f"Тестовый товар ({suffix})",
            sku=sku,
            gtin=None,
            category=category,
            price=Decimal("1.00"),
            width=round(random.uniform(50.0, 100.0), 1),
            height=round(random.uniform(50.0, 200.0), 1),
            depth=round(random.uniform(40.0, 80.0), 1),
            weight=round(random.uniform(100.0, 1000.0), 1),
            is_marked=False,
        )
        StockItem.objects.update_or_create(
            product=product,
            defaults={"quantity": 24},
        )
        return Response(
            ProductBriefSerializer(product).data,
            status=status.HTTP_201_CREATED,
        )


class PlacementTaskFilter(filters.FilterSet):
    class Meta:
        model = PlacementTask
        fields = ("status", "equipment")


class PlacementTaskViewSet(viewsets.ModelViewSet):
    """Задачи на выкладку создаются системой из планограммы и склада; ручного POST нет."""

    http_method_names = ["get", "patch", "delete", "head", "options"]
    queryset = PlacementTask.objects.select_related(
        "product",
        "equipment",
        "planogram",
        "planogram__slot",
    ).all()
    permission_classes = [IsAuthenticated]
    filterset_class = PlacementTaskFilter

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            if getattr(self.request.user, "role", None) == User.Role.ADMIN:
                return PlacementTaskAdminUpdateSerializer
            return PlacementTaskUpdateSerializer
        return PlacementTaskReadSerializer

    def destroy(self, request, *args, **kwargs):
        if getattr(request.user, "role", None) != User.Role.ADMIN:
            return Response(
                {"detail": "Удалять задачи может только администратор."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


class PlanogramFilter(filters.FilterSet):
    class Meta:
        model = Planogram
        fields = ("slot", "product")


class PlanogramViewSet(viewsets.ModelViewSet):
    queryset = Planogram.objects.select_related("slot", "slot__equipment", "product").all()
    filterset_class = PlanogramFilter

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsRoleAdmin()]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return PlanogramWriteSerializer
        return PlanogramReadSerializer


class StockItemFilter(filters.FilterSet):
    class Meta:
        model = StockItem
        fields = ("product",)


class StockItemViewSet(viewsets.ModelViewSet):
    queryset = StockItem.objects.select_related("product").all()
    serializer_class = StockItemSerializer
    filterset_class = StockItemFilter

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsRoleAdmin()]
