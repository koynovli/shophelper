"""Агрегированная аналитика по товарам для панели управляющего (склад / зал / задачи)."""

from __future__ import annotations

import csv
from datetime import timedelta
from io import StringIO

from django.db.models import (
    Exists,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Category,
    Inventory,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    StockItem,
    Store,
)
from .permissions import IsRoleAdmin

EXPIRING_DAYS = 3


def resolve_store_id(request) -> int | None:
    raw = request.query_params.get("store")
    if raw is not None and str(raw).strip() != "":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    user = request.user
    sid = getattr(user, "store_id", None)
    if sid:
        return int(sid)
    first = Store.objects.order_by("pk").values_list("id", flat=True).first()
    return int(first) if first is not None else None


def product_tracking_base_qs(store_id: int):
    """Товары, связанные с магазином: партии, планограммы зала, остатки Inventory, задачи."""
    return (
        Product.objects.filter(
            Q(batches__store_id=store_id)
            | Q(floor_planograms__slot__equipment__zone__store_id=store_id)
            | Q(inventories__store_id=store_id)
            | Q(
                placement_tasks__equipment__zone__store_id=store_id,
                placement_tasks__status__in=(
                    PlacementTask.Status.PENDING,
                    PlacementTask.Status.IN_PROGRESS,
                ),
            )
        )
        .select_related("category")
        .distinct()
    )


def annotate_product_tracking(qs, store_id: int):
    today = timezone.localdate()
    soon = today + timedelta(days=EXPIRING_DAYS)

    batch_sum = (
        ProductBatch.objects.filter(
            product_id=OuterRef("pk"),
            store_id=store_id,
            is_active=True,
        )
        .values("product_id")
        .annotate(s=Sum("current_quantity"))
        .values("s")[:1]
    )
    stock_qty = StockItem.objects.filter(product_id=OuterRef("pk")).values("quantity")[:1]
    hall_sum = (
        Inventory.objects.filter(
            product_id=OuterRef("pk"),
            store_id=store_id,
            status=Inventory.LocationStatus.SHELF,
        )
        .values("product_id")
        .annotate(s=Sum("quantity"))
        .values("s")[:1]
    )
    pending_sum = (
        PlacementTask.objects.filter(
            product_id=OuterRef("pk"),
            status__in=(
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        )
        .values("product_id")
        .annotate(s=Sum("quantity"))
        .values("s")[:1]
    )
    plan_target_sum = (
        Planogram.objects.filter(
            product_id=OuterRef("pk"),
            slot__equipment__zone__store_id=store_id,
        )
        .values("product_id")
        .annotate(s=Sum("target_quantity"))
        .values("s")[:1]
    )
    expiring_exists = Exists(
        ProductBatch.objects.filter(
            product_id=OuterRef("pk"),
            store_id=store_id,
            is_active=True,
            current_quantity__gt=0,
            expiration_date__gte=today,
            expiration_date__lte=soon,
        )
    )

    return qs.annotate(
        total_quantity=Coalesce(
            Subquery(batch_sum, output_field=IntegerField()),
            0,
        ),
        warehouse_qty=Coalesce(
            Subquery(stock_qty, output_field=IntegerField()),
            0,
        ),
        hall_qty=Coalesce(
            Subquery(hall_sum, output_field=IntegerField()),
            0,
        ),
        pending_qty=Coalesce(
            Subquery(pending_sum, output_field=IntegerField()),
            0,
        ),
        planogram_target_sum=Coalesce(
            Subquery(plan_target_sum, output_field=IntegerField()),
            0,
        ),
        has_expiring_batch=expiring_exists,
    )


def compute_tracking_status(obj) -> str:
    """OK | LOW_STOCK | EXPIRING (приоритет срока годности)."""
    if getattr(obj, "has_expiring_batch", False):
        return "EXPIRING"
    hall = int(getattr(obj, "hall_qty", 0) or 0)
    target = int(getattr(obj, "planogram_target_sum", 0) or 0)
    wh = int(getattr(obj, "warehouse_qty", 0) or 0)
    if target > 0 and hall < target:
        return "LOW_STOCK"
    if target > 0 and wh == 0 and hall < target:
        return "LOW_STOCK"
    return "OK"


def build_product_locations(product_id: int, store_id: int) -> list[dict]:
    rows = []
    for pg in (
        Planogram.objects.filter(
            product_id=product_id,
            slot__equipment__zone__store_id=store_id,
        )
        .select_related("slot", "slot__equipment")
        .order_by("slot__equipment_id", "slot__row_index", "slot__col_index")
    ):
        eq = pg.slot.equipment
        r, c = pg.slot.row_index, pg.slot.col_index
        rows.append(
            {
                "kind": "planogram",
                "planogram_id": pg.pk,
                "equipment_id": eq.id,
                "equipment_name": eq.name,
                "slot_row": r,
                "slot_col": c,
                "label": f"{eq.name}, Полка {r + 1}, Ячейка {c + 1}",
                "target_quantity": pg.target_quantity,
                "quantity": None,
            }
        )
    for inv in (
        Inventory.objects.filter(
            product_id=product_id,
            store_id=store_id,
            status=Inventory.LocationStatus.SHELF,
        )
        .select_related("shelf", "shelf__equipment")
        .iterator(chunk_size=50)
    ):
        if inv.shelf_id is None:
            continue
        eq = inv.shelf.equipment
        lvl = int(inv.shelf.level)
        rows.append(
            {
                "kind": "inventory_shelf",
                "planogram_id": None,
                "equipment_id": eq.id,
                "equipment_name": eq.name,
                "slot_row": max(0, lvl - 1),
                "slot_col": 0,
                "label": f"{eq.name}, Полка (уровень {lvl}), {inv.quantity} шт.",
                "target_quantity": None,
                "quantity": inv.quantity,
            }
        )
    return rows


class ProductTrackingRowSerializer(serializers.ModelSerializer):
    """Строка сводки: поля из annotate_product_tracking на модели Product."""

    category = serializers.SerializerMethodField()
    total_quantity = serializers.IntegerField(read_only=True)
    warehouse_qty = serializers.IntegerField(read_only=True)
    hall_qty = serializers.IntegerField(read_only=True)
    pending_qty = serializers.IntegerField(read_only=True)
    planogram_target_sum = serializers.IntegerField(read_only=True)
    status = serializers.SerializerMethodField()
    under_floor_target = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "category",
            "total_quantity",
            "warehouse_qty",
            "hall_qty",
            "pending_qty",
            "planogram_target_sum",
            "status",
            "under_floor_target",
        )

    def get_category(self, obj: Product):
        if obj.category_id is None:
            return None
        return {"id": obj.category_id, "name": obj.category.name}

    def get_status(self, obj: Product) -> str:
        return compute_tracking_status(obj)

    def get_under_floor_target(self, obj: Product) -> bool:
        t = int(getattr(obj, "planogram_target_sum", 0) or 0)
        h = int(getattr(obj, "hall_qty", 0) or 0)
        return t > 0 and h < t


class ProductTrackingDetailSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()
    batches = serializers.SerializerMethodField()
    locations = serializers.SerializerMethodField()
    map_equipment_ids = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    warehouse_qty = serializers.SerializerMethodField()
    hall_qty = serializers.SerializerMethodField()
    pending_qty = serializers.SerializerMethodField()
    planogram_target_sum = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "category",
            "total_quantity",
            "warehouse_qty",
            "hall_qty",
            "pending_qty",
            "planogram_target_sum",
            "status",
            "batches",
            "locations",
            "map_equipment_ids",
        )

    def get_category(self, obj: Product):
        if obj.category_id is None:
            return None
        return {"id": obj.category_id, "name": obj.category.name}

    def _agg(self, obj: Product):
        row = self.context.get("agg_row")
        if row is not None and row.pk == obj.pk:
            return row
        sid = int(self.context["store_id"])
        return annotate_product_tracking(Product.objects.filter(pk=obj.pk), sid).first()

    def get_total_quantity(self, obj: Product) -> int:
        r = self._agg(obj)
        return int(getattr(r, "total_quantity", 0) or 0) if r else 0

    def get_warehouse_qty(self, obj: Product) -> int:
        r = self._agg(obj)
        return int(getattr(r, "warehouse_qty", 0) or 0) if r else 0

    def get_hall_qty(self, obj: Product) -> int:
        r = self._agg(obj)
        return int(getattr(r, "hall_qty", 0) or 0) if r else 0

    def get_pending_qty(self, obj: Product) -> int:
        r = self._agg(obj)
        return int(getattr(r, "pending_qty", 0) or 0) if r else 0

    def get_planogram_target_sum(self, obj: Product) -> int:
        r = self._agg(obj)
        return int(getattr(r, "planogram_target_sum", 0) or 0) if r else 0

    def get_status(self, obj: Product) -> str:
        r = self._agg(obj)
        return compute_tracking_status(r) if r else "OK"

    def get_batches(self, obj: Product):
        sid = int(self.context["store_id"])
        out = []
        for b in (
            ProductBatch.objects.filter(product_id=obj.pk, store_id=sid)
            .order_by("expiration_date", "pk")
            .iterator(chunk_size=100)
        ):
            out.append(
                {
                    "id": b.pk,
                    "expiration_date": b.expiration_date.isoformat(),
                    "current_quantity": b.current_quantity,
                    "initial_quantity": b.initial_quantity,
                    "is_active": b.is_active,
                    "days_to_expiry": b.get_remaining_days(),
                }
            )
        return out

    def get_locations(self, obj: Product):
        cached = self.context.get("locations_cache")
        if cached is not None:
            return cached
        sid = int(self.context["store_id"])
        return build_product_locations(obj.pk, sid)

    def get_map_equipment_ids(self, obj: Product):
        locs = self.context.get("locations_cache")
        if locs is None:
            locs = self.get_locations(obj)
        return sorted({row["equipment_id"] for row in locs})


class ProductTrackingPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class ProductTrackingListView(generics.ListAPIView):
    """
    Список товаров с агрегатами: партии, склад (StockItem), зал (Inventory shelf),
    активные задачи (PENDING/IN_PROGRESS), цель по планограмме, статус.
    """

    permission_classes = [IsAuthenticated, IsRoleAdmin]
    serializer_class = ProductTrackingRowSerializer
    pagination_class = ProductTrackingPagination

    def get_queryset(self):
        store_id = resolve_store_id(self.request)
        if store_id is None:
            return Product.objects.none()

        qs = product_tracking_base_qs(store_id)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        cat = self.request.query_params.get("category")
        if cat is not None and str(cat).strip() != "":
            try:
                qs = qs.filter(category_id=int(cat))
            except (TypeError, ValueError):
                pass

        qs = annotate_product_tracking(qs, store_id)

        st = (self.request.query_params.get("status") or "").strip().upper()
        if st in ("DEFICIT", "LOW_STOCK"):
            qs = qs.filter(Q(planogram_target_sum__gt=F("hall_qty")) & Q(planogram_target_sum__gt=0))
        elif st in ("NORMAL", "OK"):
            qs = qs.filter(
                ~Q(has_expiring_batch=True),
                Q(planogram_target_sum__lte=F("hall_qty")) | Q(planogram_target_sum=0),
            )
        elif st == "EXPIRING":
            qs = qs.filter(has_expiring_batch=True)

        return qs.order_by("name", "pk")

    def list(self, request, *args, **kwargs):
        if resolve_store_id(request) is None:
            return Response(
                {"detail": "Укажите query-параметр store или привяжите магазин к пользователю."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if request.query_params.get("format") == "csv":
            qs = self.filter_queryset(self.get_queryset())
            buf = StringIO()
            w = csv.writer(buf)
            w.writerow(
                [
                    "id",
                    "name",
                    "category",
                    "total_quantity",
                    "warehouse_qty",
                    "hall_qty",
                    "pending_qty",
                    "planogram_target_sum",
                    "status",
                    "under_floor_target",
                ],
            )
            for row in qs.iterator(chunk_size=200):
                st = compute_tracking_status(row)
                target = int(getattr(row, "planogram_target_sum", 0) or 0)
                hall = int(getattr(row, "hall_qty", 0) or 0)
                under = target > 0 and hall < target
                w.writerow(
                    [
                        row.pk,
                        row.name,
                        row.category.name if row.category_id else "",
                        int(getattr(row, "total_quantity", 0) or 0),
                        int(getattr(row, "warehouse_qty", 0) or 0),
                        hall,
                        int(getattr(row, "pending_qty", 0) or 0),
                        target,
                        st,
                        "1" if under else "0",
                    ],
                )
            data = "\ufeff" + buf.getvalue()
            resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = 'attachment; filename="product_tracking.csv"'
            return resp
        return super().list(request, *args, **kwargs)


class ProductTrackingDetailView(generics.RetrieveAPIView):
    """Партии товара и позиции в зале (планограммы / учёт на полке)."""

    permission_classes = [IsAuthenticated, IsRoleAdmin]
    serializer_class = ProductTrackingDetailSerializer
    queryset = Product.objects.select_related("category").all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        sid = resolve_store_id(self.request)
        ctx["store_id"] = sid
        pk = self.kwargs.get("pk")
        if sid is not None and pk is not None:
            try:
                pid = int(pk)
            except (TypeError, ValueError):
                pid = None
            if pid is not None:
                ctx["agg_row"] = annotate_product_tracking(
                    Product.objects.filter(pk=pid), sid
                ).first()
                ctx["locations_cache"] = build_product_locations(pid, sid)
        return ctx

    def retrieve(self, request, *args, **kwargs):
        store_id = resolve_store_id(request)
        if store_id is None:
            return Response(
                {"detail": "Укажите query-параметр store или привяжите магазин к пользователю."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().retrieve(request, *args, **kwargs)


class ProductTrackingCategoriesView(APIView):
    """Категории товаров, которые встречаются в сводке по магазину (для фильтра)."""

    permission_classes = [IsAuthenticated, IsRoleAdmin]

    def get(self, request):
        sid = resolve_store_id(request)
        if sid is None:
            return Response(
                {"detail": "Укажите query-параметр store или привяжите магазин к пользователю."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cat_ids = (
            product_tracking_base_qs(sid)
            .values_list("category_id", flat=True)
            .distinct()
        )
        rows = Category.objects.filter(pk__in=cat_ids).order_by("name")
        return Response([{"id": c.pk, "name": c.name} for c in rows])
