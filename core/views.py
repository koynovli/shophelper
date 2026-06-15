from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
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
    ChatMessage,
    Equipment,
    EquipmentSlot,
    Inventory,
    PlacementChatMessage,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    ShelfClearingTask,
    StaffTask,
    StockItem,
    Supplier,
    SupplyOrder,
    SupplyOrderItem,
    SupplyReceivingTask,
    User,
    Store,
    StoreMap,
    WriteOffTask,
    Zone,
)
from .permissions import IsRoleAdmin
from .placement_chat_service import PlacementChatError, post_placement_chat_message
from .placement_execution import (
    PlacementExecutionError,
    accept_placement_task,
    complete_placement_task,
    fail_placement_task,
)
from .placement_scan_service import (
    PlacementScanError,
    find_best_task_for_scan,
    get_picking_list,
    record_placement_scan,
    scan_check_for_picking,
)
from .placement_sync import adjust_slot_quantity
from .scan_service import resolve_scan
from .product_tracking import resolve_store_id
from .serializers import (
    CategorySerializer,
    ChatMessageCreateSerializer,
    ChatMessageSerializer,
    EquipmentSerializer,
    InventorySerializer,
    PlacementTaskAdminUpdateSerializer,
    PlanogramReadSerializer,
    PlanogramWriteSerializer,
    PlacementChatMessageSerializer,
    PlacementTaskReadSerializer,
    PlacementTaskUpdateSerializer,
    ShelfClearingTaskCreateSerializer,
    ShelfClearingTaskReadSerializer,
    ProductBatchSerializer,
    ProductBriefSerializer,
    ProductCreateSerializer,
    ProductListSerializer,
    ProductSerializer,
    ShelfSerializer,
    ScanRawCodeSerializer,
    StaffTaskAdminUpdateSerializer,
    StaffTaskReadSerializer,
    StaffTaskWriteSerializer,
    StockItemSerializer,
    SupplierCreateSerializer,
    SupplierSerializer,
    ReceivingCompleteSerializer,
    SupplyOrderCreateSerializer,
    SupplyOrderCancelSerializer,
    SupplyOrderListSerializer,
    SupplyOrderSerializer,
    SupplyOrderUpdateSerializer,
    SupplyReceivingTaskReadSerializer,
    StoreMapSerializer,
    WriteOffTaskCreateSerializer,
    WriteOffTaskReadSerializer,
    ZoneSerializer,
)
from .supply_order_service import SupplyOrderError, cancel_supply_order
from .supply_receiving_service import (
    SupplyReceivingError,
    accept_receiving_task,
    complete_receiving_task,
    create_receiving_task,
)
from .staff_task_service import StaffTaskError, cancel_staff_task, create_staff_task
from .staff_task_service import accept_staff_task as accept_staff_task_svc
from .staff_task_service import complete_staff_task as complete_staff_task_svc
from .staff_task_service import post_chat_message
from .shelf_clearing_service import (
    ShelfClearingError,
    accept_shelf_clearing_task,
    cancel_shelf_clearing_task,
    complete_shelf_clearing_task,
    create_shelf_clearing_task,
)
from .write_off_service import (
    WriteOffError,
    accept_write_off_task,
    cancel_write_off_task,
    complete_write_off_task,
    create_manual_warehouse_write_off_task,
    scan_expired_write_off_tasks,
)
from .task_pool import fetch_task_pool


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


class ScanResolveView(APIView):
    """JWT: разбор кода маркировки / EAN / SKU в контексте магазина сотрудника."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ScanRawCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        store_id = resolve_store_id(request)
        result = resolve_scan(serializer.validated_data["raw_code"], store_id)
        return Response(
            result.to_dict(
                product_serializer=ProductSerializer,
                batch_serializer=ProductBatchSerializer,
            ),
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


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.order_by("name")
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return SupplierCreateSerializer
        return SupplierSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsRoleAdmin()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supplier = serializer.save()
        out = SupplierSerializer(supplier, context=self.get_serializer_context())
        headers = self.get_success_headers(out.data)
        return Response(out.data, status=status.HTTP_201_CREATED, headers=headers)


class SupplyOrderViewSet(viewsets.ModelViewSet):
    queryset = SupplyOrder.objects.prefetch_related(
        "items__product",
        "receiving_task__assigned_to",
    ).select_related(
        "company",
        "store",
        "supplier",
        "created_by",
        "received_by",
        "cancelled_by",
    )

    def get_serializer_class(self):
        if self.action == "create":
            return SupplyOrderCreateSerializer
        if self.action in ("update", "partial_update"):
            return SupplyOrderUpdateSerializer
        if self.action in ("list", "retrieve", "submit"):
            return SupplyOrderListSerializer
        return SupplyOrderSerializer

    def get_permissions(self):
        if self.action in (
            "create",
            "update",
            "partial_update",
            "destroy",
            "receive",
            "submit",
            "cancel",
        ):
            return [IsAuthenticated(), IsRoleAdmin()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        out = SupplyOrderListSerializer(
            order, context=self.get_serializer_context()
        )
        headers = self.get_success_headers(out.data)
        return Response(out.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        out = SupplyOrderListSerializer(
            order, context=self.get_serializer_context()
        )
        return Response(out.data)

    def perform_destroy(self, instance: SupplyOrder) -> None:
        if instance.status != SupplyOrder.Status.DRAFT:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"detail": "Удалить можно только черновик заказа."}
            )
        instance.delete()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        order = self.get_object()
        if order.status != SupplyOrder.Status.DRAFT:
            return Response(
                {"detail": "Оформить можно только заказ в статусе «Черновик»."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not order.items.exists():
            return Response(
                {"detail": "Добавьте позиции в заказ перед оформлением."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        update_fields = ["status"]
        planned_raw = request.data.get("planned_receiving_date")
        if planned_raw is not None:
            if planned_raw == "":
                order.planned_receiving_date = None
            else:
                from django.utils.dateparse import parse_date

                parsed = parse_date(str(planned_raw))
                if parsed is None:
                    return Response(
                        {"planned_receiving_date": "Ожидается дата YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                order.planned_receiving_date = parsed
            update_fields.append("planned_receiving_date")

        order.status = SupplyOrder.Status.ORDERED
        order.save(update_fields=update_fields)

        assigned_to = None
        assigned_raw = request.data.get("assigned_to")
        if assigned_raw is not None:
            try:
                assigned_to = User.objects.get(
                    pk=int(assigned_raw),
                    role=User.Role.EMPLOYEE,
                )
            except (User.DoesNotExist, TypeError, ValueError):
                return Response(
                    {"assigned_to": "Укажите id сотрудника с ролью employee."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            create_receiving_task(order, request.user, assigned_to=assigned_to)
        except SupplyReceivingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        order = self.get_object()
        serializer = SupplyOrderListSerializer(
            order, context=self.get_serializer_context()
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = SupplyOrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = cancel_supply_order(
                int(pk),
                request.user,
                reason_code=serializer.validated_data["reason_code"],
                reason_note=serializer.validated_data.get("reason_note", ""),
            )
        except SupplyOrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        order = self.get_queryset().get(pk=order.pk)
        return Response(
            SupplyOrderListSerializer(order, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        return Response(
            {
                "detail": "Приёмка выполняется сотрудником через задачу приёмки "
                "(PWA → задача «Приёмка»)."
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class SupplyReceivingTaskViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SupplyReceivingTask.objects.select_related(
        "supply_order",
        "supply_order__supplier",
        "supply_order__store",
        "assigned_to",
    ).prefetch_related(
        "supply_order__items__product",
        "supply_order__receiving_task__assigned_to",
    )
    serializer_class = SupplyReceivingTaskReadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "role", None) == User.Role.EMPLOYEE:
            qs = qs.filter(
                status__in=(
                    SupplyReceivingTask.Status.CREATED,
                    SupplyReceivingTask.Status.IN_PROGRESS,
                )
            ).filter(Q(assigned_to_id=user.pk) | Q(assigned_to__isnull=True))
        return qs

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        try:
            task = accept_receiving_task(int(pk), request.user)
        except SupplyReceivingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SupplyReceivingTaskReadSerializer(task).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        serializer = ReceivingCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lines = [
            {
                "item_id": row["item_id"],
                "manufacture_date": row.get("manufacture_date"),
                "actual_quantity": row["actual_quantity"],
                "discrepancy_note": row.get("discrepancy_note", ""),
            }
            for row in serializer.validated_data["lines"]
        ]
        try:
            task = complete_receiving_task(int(pk), request.user, lines)
        except SupplyReceivingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        task = SupplyReceivingTask.objects.select_related(
            "supply_order__supplier",
            "supply_order__store",
            "assigned_to",
        ).prefetch_related("supply_order__items__product").get(pk=task.pk)
        return Response(
            SupplyReceivingTaskReadSerializer(task).data,
            status=status.HTTP_200_OK,
        )


class EmployeeListView(APIView):
    """Список сотрудников для назначения задачи приёмки."""

    permission_classes = [IsAuthenticated, IsRoleAdmin]

    def get(self, request):
        rows = User.objects.filter(role=User.Role.EMPLOYEE).order_by("username")
        return Response(
            [{"id": u.pk, "username": u.username} for u in rows],
            status=status.HTTP_200_OK,
        )


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


class StoreMapView(APIView):
    """Границы 2D-карты зала для текущего магазина пользователя."""

    def get(self, request):
        store_id = getattr(request.user, "store_id", None)
        floor_map = None
        if store_id:
            floor_map = StoreMap.objects.filter(store_id=store_id).first()
        if floor_map is None:
            floor_map = StoreMap.objects.select_related("store").first()
        if floor_map is None:
            store = Store.objects.first()
            if store is None:
                return Response(
                    {"detail": "Магазин не настроен."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            floor_map, _ = StoreMap.objects.get_or_create(
                store=store,
                defaults={"width_m": 20.0, "length_m": 15.0},
            )
        return Response(StoreMapSerializer(floor_map).data)


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.select_related("store").prefetch_related(
        "equipment__shelves",
        "equipment__slots",
        "equipment__slots__planograms",
        "equipment__slots__planograms__product",
        "equipment__slots__planograms__placement_tasks",
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
        if self.action in ("modification_info",):
            return [IsAuthenticated(), IsRoleAdmin()]
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsRoleAdmin()]

    def perform_destroy(self, instance: Equipment) -> None:
        from .equipment_modification_guard import ensure_equipment_can_be_deleted

        ensure_equipment_can_be_deleted(instance)
        instance.delete()

    @action(detail=True, methods=["get"], url_path="modification-info")
    def modification_info(self, request, pk=None):
        from .equipment_modification_guard import assess_equipment_modification

        equipment = self.get_object()
        return Response(assess_equipment_modification(equipment).to_dict())


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

    def get_permissions(self):
        if self.action in ("write_off_expired", "scan_write_off_tasks"):
            return [IsAuthenticated(), IsRoleAdmin()]
        return super().get_permissions()

    @action(detail=False, methods=["post"], url_path="scan-write-off-tasks")
    def scan_write_off_tasks(self, request):
        """Сканирует просрочку на складе и полках; создаёт задания сотрудникам."""
        store_id = resolve_store_id(request)
        dry_run = request.query_params.get("dry_run", "").lower() in ("1", "true", "yes")
        result = scan_expired_write_off_tasks(store_id, dry_run=dry_run)
        return Response(result.to_dict(), status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="write-off-expired")
    def write_off_expired(self, request):
        """Устаревший endpoint: перенаправляет на scan-write-off-tasks."""
        store_id = resolve_store_id(request)
        dry_run = request.query_params.get("dry_run", "").lower() in ("1", "true", "yes")
        result = scan_expired_write_off_tasks(store_id, dry_run=dry_run)
        legacy = {
            "dry_run": result.dry_run,
            "slots_written_off": result.shelf_tasks,
            "units_written_off": result.shelf_units,
            "entries": [
                e
                for e in result.to_dict()["entries"]
                if e["location"] == "SHELF"
            ],
        }
        return Response(legacy, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def shelf_fill_report(self, request):
        """
        Отчёт заполненности: слоты с планограммой (current_qty / max_capacity)
        и legacy-срез по Inventory на полке.
        """
        slot_rows = []
        planograms = Planogram.objects.select_related(
            "slot",
            "slot__equipment",
            "slot__equipment__zone",
            "product",
        ).order_by("slot__equipment_id", "slot__row_index", "slot__col_index")
        for pg in planograms:
            slot = pg.slot
            cap = int(slot.max_capacity or 0)
            current = int(slot.current_qty or 0)
            fill_percent = (
                min(100.0, round(current / cap * 100, 2)) if cap > 0 else None
            )
            slot_rows.append(
                {
                    "source": "slot",
                    "slot_id": slot.pk,
                    "planogram_id": pg.pk,
                    "product_id": pg.product_id,
                    "product_name": pg.product.name,
                    "row_index": slot.row_index,
                    "col_index": slot.col_index,
                    "equipment_id": slot.equipment_id,
                    "equipment_name": slot.equipment.name,
                    "zone_name": slot.equipment.zone.name,
                    "current_qty": current,
                    "max_capacity": cap,
                    "fill_percent": fill_percent,
                    "below_30_percent": cap > 0 and current < cap * 0.3,
                }
            )

        shelves = Shelf.objects.select_related(
            "equipment",
            "equipment__zone",
        ).order_by("equipment_id", "level")

        shelf_rows = []
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

            shelf_rows.append(
                {
                    "source": "inventory",
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

        return Response(
            {"slots": slot_rows, "shelves_inventory": shelf_rows},
            status=status.HTTP_200_OK,
        )


class CategoryViewSet(viewsets.ModelViewSet):
    """Категории номенклатуры: список для всех, создание — админ."""

    queryset = Category.objects.order_by("name")
    serializer_class = CategorySerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsRoleAdmin()]
        return [IsAuthenticated()]


class ProductViewSet(viewsets.ModelViewSet):
    """Номенклатура: каталог (read) и регистрация/правка (admin)."""

    queryset = Product.objects.select_related("category").order_by("name")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return ProductListSerializer
        if self.action in ("create", "update", "partial_update"):
            return ProductCreateSerializer
        return ProductBriefSerializer

    def get_permissions(self):
        if self.action in (
            "create",
            "update",
            "partial_update",
            "destroy",
            "delete_info",
        ):
            return [IsAuthenticated(), IsRoleAdmin()]
        return [IsAuthenticated()]

    def perform_destroy(self, instance: Product) -> None:
        from .product_delete_guard import ensure_product_can_be_deleted

        ensure_product_can_be_deleted(instance)
        instance.delete()

    @action(detail=True, methods=["get"], url_path="delete-info")
    def delete_info(self, request, pk=None):
        from .product_delete_guard import assess_product_deletion

        product = self.get_object()
        return Response(assess_product_deletion(product).to_dict())


class PlacementTaskFilter(filters.FilterSet):
    class Meta:
        model = PlacementTask
        fields = ("status", "equipment")


class PlacementTaskViewSet(viewsets.ModelViewSet):
    """Задачи на выкладку создаются системой из планограммы и склада; ручного POST нет."""

    http_method_names = ["get", "patch", "delete", "head", "options", "post"]
    queryset = PlacementTask.objects.select_related(
        "product",
        "equipment",
        "planogram",
        "planogram__slot",
        "assigned_to",
        "batch",
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

    @action(detail=False, methods=["get"], url_path="picking-list")
    def picking_list(self, request):
        store_id = resolve_store_id(request)
        items = get_picking_list(request.user, store_id)
        return Response(items)

    @action(detail=False, methods=["post"], url_path="scan-check")
    def scan_check(self, request):
        serializer = ScanRawCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        store_id = resolve_store_id(request)
        raw_code = serializer.validated_data["raw_code"]
        data = scan_check_for_picking(
            request.user,
            raw_code=raw_code,
            store_id=store_id,
        )
        best = find_best_task_for_scan(
            request.user,
            raw_code=raw_code,
            store_id=store_id,
        )
        if best.get("best_task"):
            data["best_task"] = best["best_task"]
            data["message"] = best["message"]
        return Response(data)

    @action(detail=True, methods=["post"], url_path="scan-unit")
    def scan_unit(self, request, pk=None):
        serializer = ScanRawCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        store_id = resolve_store_id(request)
        try:
            task, resolved = record_placement_scan(
                int(pk),
                request.user,
                raw_code=serializer.validated_data.get("raw_code") or "",
                store_id=store_id,
                weight_kg=serializer.validated_data.get("weight_kg"),
            )
        except PlacementScanError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = PlacementTaskReadSerializer(task).data
        payload["scan_message"] = resolved.message
        return Response(payload)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        try:
            task = accept_placement_task(int(pk), request.user)
        except PlacementExecutionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PlacementTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        photo = request.FILES.get("photo")
        try:
            task = complete_placement_task(int(pk), request.user, photo)
        except PlacementExecutionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PlacementTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"], url_path="fail")
    def fail_action(self, request, pk=None):
        reason = (request.data.get("reason") or "").strip()
        try:
            task = fail_placement_task(int(pk), request.user, reason=reason)
        except PlacementExecutionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PlacementTaskReadSerializer(task).data)

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, pk=None):
        task = self.get_object()
        if request.method == "GET":
            qs = PlacementChatMessage.objects.filter(placement_task=task).select_related(
                "sender",
            )
            return Response(PlacementChatMessageSerializer(qs, many=True).data)
        text = (request.data.get("text") or "").strip()
        image = request.FILES.get("image")
        try:
            message = post_placement_chat_message(
                task.pk,
                request.user,
                text=text,
                image_file=image,
            )
        except PlacementChatError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            PlacementChatMessageSerializer(message).data,
            status=status.HTTP_201_CREATED,
        )


class ShelfClearingTaskFilter(filters.FilterSet):
    class Meta:
        model = ShelfClearingTask
        fields = ("status", "equipment", "slot")


class ShelfClearingTaskViewSet(viewsets.ModelViewSet):
    """Задания на уборку товара с полки на склад (создаёт менеджер)."""

    http_method_names = ["get", "post", "delete", "head", "options"]
    queryset = ShelfClearingTask.objects.select_related(
        "product",
        "equipment",
        "slot",
        "planogram",
        "assigned_to",
        "batch",
    ).all()
    permission_classes = [IsAuthenticated]
    filterset_class = ShelfClearingTaskFilter

    def get_serializer_class(self):
        if self.action == "create":
            return ShelfClearingTaskCreateSerializer
        return ShelfClearingTaskReadSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsRoleAdmin()]
        if self.action == "destroy":
            return [IsAuthenticated(), IsRoleAdmin()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = ShelfClearingTaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            task = create_shelf_clearing_task(
                request.user,
                slot_id=serializer.validated_data["slot_id"],
            )
        except ShelfClearingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ShelfClearingTaskReadSerializer(task).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        try:
            task = cancel_shelf_clearing_task(int(kwargs["pk"]), request.user)
        except ShelfClearingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ShelfClearingTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        try:
            task = accept_shelf_clearing_task(int(pk), request.user)
        except ShelfClearingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ShelfClearingTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        photo = request.FILES.get("photo")
        raw_code = (request.data.get("raw_code") or "").strip()
        try:
            task = complete_shelf_clearing_task(
                int(pk),
                request.user,
                photo,
                raw_code=raw_code,
                store_id=resolve_store_id(request),
            )
        except ShelfClearingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ShelfClearingTaskReadSerializer(task).data)


class WriteOffTaskFilter(filters.FilterSet):
    class Meta:
        model = WriteOffTask
        fields = ("status", "location", "product", "batch")


class WriteOffTaskViewSet(viewsets.ModelViewSet):
    """Задания на списание товара (склад / полка)."""

    http_method_names = ["get", "post", "delete", "head", "options"]
    queryset = WriteOffTask.objects.select_related(
        "product",
        "batch",
        "store",
        "slot",
        "equipment",
        "planogram",
        "assigned_to",
        "created_by",
    ).all()
    permission_classes = [IsAuthenticated]
    filterset_class = WriteOffTaskFilter

    def get_serializer_class(self):
        if self.action == "create":
            return WriteOffTaskCreateSerializer
        return WriteOffTaskReadSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsRoleAdmin()]
        if self.action == "destroy":
            return [IsAuthenticated(), IsRoleAdmin()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = WriteOffTaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            task = create_manual_warehouse_write_off_task(
                request.user,
                batch_id=data["batch_id"],
                quantity=data["quantity"],
                reason=data.get("reason", ""),
            )
        except WriteOffError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            WriteOffTaskReadSerializer(task).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        try:
            task = cancel_write_off_task(int(kwargs["pk"]), request.user)
        except WriteOffError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WriteOffTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        try:
            task = accept_write_off_task(int(pk), request.user)
        except WriteOffError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WriteOffTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        photo = request.FILES.get("photo")
        raw_code = (request.data.get("raw_code") or "").strip()
        try:
            task = complete_write_off_task(
                int(pk),
                request.user,
                photo,
                raw_code=raw_code,
                store_id=resolve_store_id(request),
            )
        except WriteOffError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WriteOffTaskReadSerializer(task).data)


class EquipmentSlotAdjustView(APIView):
    """Симуляция продажи/коррекции остатка на слоте (уменьшает current_qty)."""

    permission_classes = [IsAuthenticated, IsRoleAdmin]

    def post(self, request, pk: int):
        from decimal import Decimal, ROUND_HALF_UP

        from .product_units import product_stores_weight

        slot = (
            EquipmentSlot.objects.select_related("equipment")
            .prefetch_related("planograms__product")
            .filter(pk=pk)
            .first()
        )
        if slot is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        planogram = slot.planograms.first()
        product = planogram.product if planogram else None
        is_weight = product_stores_weight(product)

        delta_kg_raw = request.data.get("delta_kg")
        if is_weight:
            if delta_kg_raw is None or str(delta_kg_raw).strip() == "":
                return Response(
                    {
                        "detail": "Для весового товара укажите delta_kg (например, \"-0.250\")."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            kg = Decimal(str(delta_kg_raw))
            delta = int((kg * Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            delta = int(request.data.get("delta", 0))

        if delta == 0:
            return Response(
                {"detail": "Укажите ненулевой delta (отрицательный — продажа)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            adjust_slot_quantity(pk, delta)
        except EquipmentSlot.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        slot = EquipmentSlot.objects.get(pk=pk)
        from .product_units import format_quantity

        return Response(
            {
                "id": slot.pk,
                "current_qty": slot.current_qty,
                "max_capacity": slot.max_capacity,
                "current_qty_display": format_quantity(product, slot.current_qty),
            },
        )


class EquipmentSlotCapacityPreviewView(APIView):
    """Предпросмотр max_capacity слота для товара (мерчандайзинг)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        product_raw = request.query_params.get("product")
        if product_raw is None or str(product_raw).strip() == "":
            return Response(
                {"detail": "Укажите query-параметр product."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            product_id = int(product_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Некорректный product."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slot = EquipmentSlot.objects.select_related("equipment").filter(pk=pk).first()
        if slot is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        product = Product.objects.filter(pk=product_id).first()
        if product is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        from .models import Equipment
        from .product_units import grams_to_kg, product_stores_weight
        from .spatial_engine import calculate_slot_max_capacity, refresh_slot_max_capacity

        is_weight = product_stores_weight(product)
        if slot.planograms.filter(product=product).exists():
            cap = refresh_slot_max_capacity(slot, product)
        else:
            cap = calculate_slot_max_capacity(slot, product)

        payload = {
            "max_capacity": cap,
            "quantity_unit": "kg" if is_weight else "piece",
            "max_capacity_kg": str(grams_to_kg(cap)) if is_weight else None,
        }
        return Response(payload)


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

    def perform_destroy(self, instance: Planogram) -> None:
        from .equipment_modification_guard import ensure_planogram_can_be_deleted

        ensure_planogram_can_be_deleted(instance)
        instance.delete()


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


class StaffTaskFilter(filters.FilterSet):
    class Meta:
        model = StaffTask
        fields = ("status", "assigned_to", "zone")


class StaffTaskViewSet(viewsets.ModelViewSet):
    queryset = StaffTask.objects.select_related(
        "created_by",
        "assigned_to",
        "zone",
        "equipment",
        "slot",
    ).all()
    permission_classes = [IsAuthenticated]
    filterset_class = StaffTaskFilter
    lookup_field = "pk"

    def get_serializer_class(self):
        if self.action in ("create",):
            return StaffTaskWriteSerializer
        if self.action in ("partial_update", "update"):
            return StaffTaskAdminUpdateSerializer
        return StaffTaskReadSerializer

    def get_permissions(self):
        if self.action in ("create", "partial_update", "update", "destroy"):
            return [IsAuthenticated(), IsRoleAdmin()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = StaffTaskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            task = create_staff_task(
                request.user,
                title=data["title"],
                description=data.get("description", ""),
                assigned_to=data.get("assigned_to"),
                zone=data.get("zone"),
                equipment=data.get("equipment"),
                slot=data.get("slot"),
                requires_photo=data.get("requires_photo", False),
            )
        except StaffTaskError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            StaffTaskReadSerializer(task).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        try:
            task = accept_staff_task_svc(pk, request.user)
        except StaffTaskError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StaffTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        photo = request.FILES.get("photo")
        try:
            task = complete_staff_task_svc(pk, request.user, photo)
        except StaffTaskError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StaffTaskReadSerializer(task).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            task = cancel_staff_task(pk, request.user)
        except StaffTaskError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StaffTaskReadSerializer(task).data)

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, pk=None):
        task = self.get_object()
        if request.method == "GET":
            qs = ChatMessage.objects.filter(staff_task=task).select_related("sender")
            return Response(
                ChatMessageSerializer(qs, many=True, context={"request": request}).data
            )
        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = request.FILES.get("image")
        try:
            message = post_chat_message(
                task.pk,
                request.user,
                text=serializer.validated_data.get("text", ""),
                image_file=image,
            )
        except StaffTaskError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ChatMessageSerializer(message, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TaskPoolView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get("status")
        task_type = request.query_params.get("task_type")
        assigned_to = request.query_params.get("assigned_to")
        assigned_to_id = int(assigned_to) if assigned_to and assigned_to.isdigit() else None
        items = fetch_task_pool(
            status=status_filter,
            task_type=task_type,
            assigned_to_id=assigned_to_id,
            user=request.user,
        )
        return Response(items)
