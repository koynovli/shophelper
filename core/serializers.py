from decimal import Decimal

from django.db import transaction
from django.db.models import Min, Sum
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Category,
    ChatMessage,
    Company,
    Equipment,
    EquipmentSlot,
    Inventory,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    StaffTask,
    StockItem,
    Store,
    StoreMap,
    Supplier,
    SupplyOrder,
    SupplyOrderItem,
    SupplyReceivingTask,
    User,
    Zone,
)
from .placement_sync import release_placement_task_reservation


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"


class ProductBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "name", "sku")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "gtin",
            "category",
            "price",
            "width",
            "height",
            "depth",
            "weight",
            "is_marked",
            "is_stackable",
            "allowed_equipment_types",
        )


class ProductCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            "name",
            "sku",
            "gtin",
            "category",
            "price",
            "width",
            "height",
            "depth",
            "weight",
            "is_marked",
            "is_stackable",
            "allowed_equipment_types",
        )
        extra_kwargs = {
            "gtin": {"required": False, "allow_null": True, "allow_blank": True},
            "is_marked": {"required": False},
            "is_stackable": {"required": False},
            "allowed_equipment_types": {"required": False},
        }

    def validate_allowed_equipment_types(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("Ожидается список типов оборудования.")
        valid = {choice[0] for choice in Equipment.EquipmentType.choices}
        normalized: list[str] = []
        for raw in value:
            eq_type = str(raw).strip()
            if eq_type not in valid:
                raise serializers.ValidationError(
                    f"Неизвестный тип оборудования: {eq_type!r}."
                )
            if eq_type not in normalized:
                normalized.append(eq_type)
        return normalized

    def validate_sku(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("SKU обязателен.")
        qs = Product.objects.filter(sku__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Товар с таким SKU уже существует.")
        return value

    def validate_gtin(self, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        value = str(value).strip()
        if not value.isdigit() or len(value) > 14:
            raise serializers.ValidationError("GTIN: до 14 цифр.")
        qs = Product.objects.filter(gtin=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Товар с таким GTIN уже существует.")
        return value

    def validate_price(self, value) -> Decimal:
        if value is None or Decimal(str(value)) < 0:
            raise serializers.ValidationError("Цена не может быть отрицательной.")
        return value

    def _validate_positive(self, value: float, label: str) -> float:
        if value is None or float(value) <= 0:
            raise serializers.ValidationError(f"{label} должно быть больше 0.")
        return float(value)

    def validate_width(self, value: float) -> float:
        return self._validate_positive(value, "Ширина")

    def validate_height(self, value: float) -> float:
        return self._validate_positive(value, "Высота")

    def validate_depth(self, value: float) -> float:
        return self._validate_positive(value, "Глубина")

    def validate_weight(self, value: float) -> float:
        return self._validate_positive(value, "Вес")


class EquipmentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Equipment
        fields = ("id", "name")


class EquipmentSlotSerializer(serializers.ModelSerializer):
    planogram = serializers.SerializerMethodField()
    active_placement_task = serializers.SerializerMethodField()
    nearest_batch_expiry = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentSlot
        fields = (
            "id",
            "row_index",
            "col_index",
            "width_percent",
            "slot_label",
            "current_qty",
            "max_capacity",
            "planogram",
            "active_placement_task",
            "nearest_batch_expiry",
        )

    def get_active_placement_task(self, obj: EquipmentSlot) -> bool:
        return obj.planograms.filter(
            placement_tasks__status__in=(
                PlacementTask.Status.CREATED,
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        ).exists()

    def get_nearest_batch_expiry(self, obj: EquipmentSlot):
        planogram = obj.planograms.select_related("product").first()
        if planogram is None:
            return None
        shelf = obj.shelf
        if shelf is None:
            shelf = Shelf.objects.filter(
                equipment_id=obj.equipment_id,
                level=obj.row_index + 1,
            ).first()
        if shelf is None:
            return None
        agg = Inventory.objects.filter(
            product_id=planogram.product_id,
            shelf_id=shelf.id,
            status=Inventory.LocationStatus.SHELF,
            batch__isnull=False,
            batch__is_active=True,
        ).aggregate(nearest=Min("batch__expiration_date"))
        return agg.get("nearest")

    def get_planogram(self, obj: EquipmentSlot):
        planogram = obj.planograms.select_related("product").first()
        if planogram is None:
            return None
        row = StockItem.objects.filter(product_id=planogram.product_id).first()
        stock_qty = int(row.quantity) if row else 0
        completed_sum = planogram.placement_tasks.filter(
            status=PlacementTask.Status.COMPLETED,
        ).aggregate(total=Sum("quantity"))["total"]
        completed_qty = int(completed_sum or 0)
        pending_sum = planogram.placement_tasks.filter(
            status__in=(
                PlacementTask.Status.CREATED,
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        ).aggregate(total=Sum("quantity"))["total"]
        pending_qty = int(pending_sum or 0)
        cap = int(obj.max_capacity or 0)
        current = int(obj.current_qty or 0)
        target = int(planogram.target_quantity)
        gap = max(0, cap - current - pending_qty) if cap > 0 else max(0, target - completed_qty - pending_qty)
        status = "OK"
        if pending_qty > 0:
            status = "IN_PROGRESS"
        elif cap > 0 and current < cap * 0.3:
            status = "DEFICIT" if stock_qty < gap else "IN_PROGRESS"
        elif gap > 0:
            status = "DEFICIT" if stock_qty < gap else "IN_PROGRESS"
        return {
            "id": planogram.pk,
            "product": ProductBriefSerializer(planogram.product).data,
            "target_quantity": planogram.target_quantity,
            "current_qty": current,
            "max_capacity": cap,
            "stock_quantity": stock_qty,
            "pending_quantity": pending_qty,
            "replenishment_status": status,
        }


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


class PlacementTaskReadSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    equipment = EquipmentBriefSerializer(read_only=True)
    assigned_to = UserBriefSerializer(read_only=True)
    slot_info = serializers.SerializerMethodField()
    destination_text = serializers.SerializerMethodField()
    slot_qr_token = serializers.SerializerMethodField()

    class Meta:
        model = PlacementTask
        fields = (
            "id",
            "planogram",
            "product",
            "equipment",
            "slot_info",
            "destination_text",
            "quantity",
            "status",
            "assigned_to",
            "batch",
            "photo_url",
            "slot_verified_at",
            "completed_at",
            "slot_qr_token",
            "created_at",
        )

    def get_slot_qr_token(self, obj: PlacementTask):
        if obj.planogram_id and obj.planogram.slot_id:
            return str(obj.planogram.slot.qr_token)
        return None

    def get_slot_info(self, obj: PlacementTask):
        if obj.planogram_id is None or obj.planogram.slot_id is None:
            return None
        slot = obj.planogram.slot
        return {
            "id": slot.id,
            "row_index": slot.row_index,
            "col_index": slot.col_index,
        }

    def get_destination_text(self, obj: PlacementTask) -> str:
        if obj.planogram_id and obj.planogram.slot_id:
            slot = obj.planogram.slot
            return (
                f"{obj.equipment.name} -> Полка {slot.row_index + 1} -> Ячейка {slot.col_index + 1}"
            )
        return obj.equipment.name


class PlacementTaskUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlacementTask
        fields = ("status",)

    def validate_status(self, value: str) -> str:
        raise serializers.ValidationError(
            "Используйте POST /placement-tasks/{id}/complete/ для завершения задачи."
        )

    def validate(self, attrs):
        if self.instance and self.instance.status == PlacementTask.Status.COMPLETED:
            raise serializers.ValidationError("Задача уже выполнена.")
        return attrs

    def update(self, instance, validated_data):
        from .placement_sync import reconcile_planogram

        instance = super().update(instance, validated_data)
        if instance.planogram_id and instance.status == PlacementTask.Status.COMPLETED:
            reconcile_planogram(instance.planogram)
        return instance


class PlacementTaskAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlacementTask
        fields = ("status", "equipment")

    def validate_status(self, value: str) -> str:
        allowed = {
            PlacementTask.Status.CREATED,
            PlacementTask.Status.PENDING,
            PlacementTask.Status.IN_PROGRESS,
            PlacementTask.Status.COMPLETED,
            PlacementTask.Status.FAILED,
            PlacementTask.Status.CANCELLED,
        }
        if value not in allowed:
            raise serializers.ValidationError("Недопустимый статус задачи.")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.status == PlacementTask.Status.COMPLETED:
            raise serializers.ValidationError("Выполненную задачу нельзя изменять.")
        if self.instance and self.instance.status == PlacementTask.Status.CANCELLED:
            raise serializers.ValidationError("Отменённую задачу нельзя изменять.")
        return attrs

    def update(self, instance, validated_data):
        from .placement_sync import reconcile_planogram

        new_status = validated_data.get("status", instance.status)
        new_equipment = validated_data.get("equipment")

        if new_status == PlacementTask.Status.CANCELLED:
            validated_data.pop("equipment", None)
            new_equipment = None

        with transaction.atomic():
            task = (
                PlacementTask.objects.select_for_update()
                .select_related("planogram", "planogram__slot")
                .get(pk=instance.pk)
            )
            if new_status == PlacementTask.Status.CANCELLED and task.status in (
                PlacementTask.Status.CREATED,
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ):
                release_placement_task_reservation(task.product_id, int(task.quantity))

            if (
                new_equipment is not None
                and new_equipment.pk != task.equipment_id
                and task.planogram_id
            ):
                old_slot = task.planogram.slot
                new_slot = (
                    EquipmentSlot.objects.select_for_update()
                    .filter(
                        equipment_id=new_equipment.pk,
                        row_index=old_slot.row_index,
                        col_index=old_slot.col_index,
                    )
                    .first()
                )
                if new_slot is None:
                    new_slot = (
                        EquipmentSlot.objects.select_for_update()
                        .filter(equipment_id=new_equipment.pk)
                        .order_by("row_index", "col_index")
                        .first()
                    )
                if new_slot is None:
                    raise serializers.ValidationError(
                        {"equipment": "У выбранного оборудования нет слотов."}
                    )
                blocking = (
                    Planogram.objects.select_for_update()
                    .filter(slot=new_slot)
                    .exclude(pk=task.planogram_id)
                    .exists()
                )
                if blocking:
                    raise serializers.ValidationError(
                        {
                            "equipment": "Целевой слот уже занят другой позицией планограммы.",
                        }
                    )
                Planogram.objects.filter(pk=task.planogram_id).update(slot=new_slot)

            instance = super().update(instance, validated_data)

        if instance.planogram_id and instance.status == PlacementTask.Status.COMPLETED:
            reconcile_planogram(instance.planogram)
        return instance


class PlanogramReadSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    slot = serializers.SerializerMethodField()
    stock_quantity = serializers.SerializerMethodField()
    current_qty = serializers.SerializerMethodField()
    max_capacity = serializers.SerializerMethodField()

    class Meta:
        model = Planogram
        fields = (
            "id",
            "slot",
            "product",
            "target_quantity",
            "current_qty",
            "max_capacity",
            "stock_quantity",
        )

    def get_current_qty(self, obj: Planogram) -> int:
        return int(obj.slot.current_qty or 0)

    def get_max_capacity(self, obj: Planogram) -> int:
        return int(obj.slot.max_capacity or 0)

    def get_stock_quantity(self, obj: Planogram) -> int:
        row = StockItem.objects.filter(product_id=obj.product_id).first()
        return int(row.quantity) if row else 0

    def get_slot(self, obj: Planogram):
        return {
            "id": obj.slot_id,
            "equipment_id": obj.slot.equipment_id,
            "row_index": obj.slot.row_index,
            "col_index": obj.slot.col_index,
        }


class PlanogramWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Planogram
        fields = ("slot", "product", "target_quantity")

    def validate_target_quantity(self, value: int) -> int:
        if value is not None and value < 1:
            raise serializers.ValidationError("Целевое количество должно быть не меньше 1.")
        return value

    def validate(self, attrs):
        slot = attrs.get("slot") or (self.instance.slot if self.instance else None)
        product = attrs.get("product") or (self.instance.product if self.instance else None)
        target_quantity = attrs.get(
            "target_quantity",
            self.instance.target_quantity if self.instance else None,
        )

        if slot is not None and product is not None:
            equipment = (
                slot.equipment
                if hasattr(slot, "equipment") and slot.equipment_id
                else Equipment.objects.filter(pk=slot.equipment_id).first()
            )
            allowed = product.allowed_equipment_types or []
            if allowed and equipment is not None:
                eq_type = str(equipment.type)
                if eq_type not in allowed:
                    raise serializers.ValidationError(
                        "Товар не предназначен для этого типа оборудования."
                    )
            if (
                equipment is not None
                and str(equipment.type) == Equipment.EquipmentType.MANNEQUIN
                and target_quantity is not None
                and int(target_quantity) > 1
            ):
                attrs["target_quantity"] = 1

        return attrs

    def _apply_capacity_defaults(self, planogram: Planogram) -> Planogram:
        from .spatial_engine import refresh_slot_max_capacity

        cap = refresh_slot_max_capacity(planogram.slot, planogram.product)
        if int(planogram.target_quantity or 0) < 1 and cap > 0:
            planogram.target_quantity = cap
            planogram.save(update_fields=["target_quantity"])
        elif cap > 0 and int(planogram.target_quantity) > cap:
            planogram.target_quantity = cap
            planogram.save(update_fields=["target_quantity"])
        return planogram

    def create(self, validated_data):
        planogram = super().create(validated_data)
        return self._apply_capacity_defaults(planogram)

    def update(self, instance, validated_data):
        planogram = super().update(instance, validated_data)
        return self._apply_capacity_defaults(planogram)


class PlacementChatMessageSerializer(serializers.ModelSerializer):
    sender = UserBriefSerializer(read_only=True)

    class Meta:
        from .models import PlacementChatMessage

        model = PlacementChatMessage
        fields = ("id", "placement_task", "sender", "text", "image_url", "created_at")
        read_only_fields = ("id", "placement_task", "sender", "image_url", "created_at")


class StockItemSerializer(serializers.ModelSerializer):
    product_detail = ProductBriefSerializer(source="product", read_only=True)

    class Meta:
        model = StockItem
        fields = ("id", "product", "product_detail", "quantity")
        read_only_fields = ("id", "product_detail")


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"


class SupplierCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ("name", "inn", "contact_info")
        extra_kwargs = {"contact_info": {"required": False, "allow_blank": True}}

    def validate_inn(self, value: str) -> str:
        digits = "".join(c for c in value if c.isdigit())
        if len(digits) not in (10, 12):
            raise serializers.ValidationError(
                "ИНН должен содержать 10 или 12 цифр."
            )
        if Supplier.objects.filter(inn=digits).exists():
            raise serializers.ValidationError("Поставщик с таким ИНН уже зарегистрирован.")
        return digits

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Укажите название поставщика.")
        return name


class ProductBatchSerializer(serializers.ModelSerializer):
    remaining_days = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    quantity = serializers.IntegerField(write_only=True, required=False, min_value=1)
    expiry_date = serializers.DateField(write_only=True, required=False)

    class Meta:
        model = ProductBatch
        fields = "__all__"
        extra_kwargs = {
            # Заполняются из quantity / expiry_date в validate() при приёмке
            "initial_quantity": {"required": False},
            "current_quantity": {"required": False},
            "expiration_date": {"required": False},
            "purchase_price": {"required": False},
            "store": {"required": False},
            "supply_item": {"required": False},
            "serial_number": {"required": False},
            "is_active": {"required": False},
            "created_at": {"read_only": True},
        }

    def get_remaining_days(self, obj: ProductBatch) -> int:
        return obj.get_remaining_days()

    def get_is_expired(self, obj: ProductBatch) -> bool:
        return obj.is_expired

    def validate(self, attrs):
        quantity = attrs.get("quantity")
        expiry_date = attrs.get("expiry_date")
        if quantity is not None:
            attrs["initial_quantity"] = quantity
            attrs["current_quantity"] = quantity
        if expiry_date is not None:
            attrs["expiration_date"] = expiry_date

        if self.instance is None:
            if attrs.get("initial_quantity") is None or attrs.get("current_quantity") is None:
                raise serializers.ValidationError("Укажите quantity (количество партии).")
            if attrs.get("expiration_date") is None:
                raise serializers.ValidationError("Укажите expiry_date (срок годности).")
            if attrs.get("purchase_price") is None:
                attrs["purchase_price"] = 0
        return attrs

    def create(self, validated_data):
        validated_data.pop("quantity", None)
        validated_data.pop("expiry_date", None)
        request = self.context.get("request")
        if validated_data.get("store") is None:
            user = getattr(request, "user", None)
            user_store = getattr(user, "store", None) if user is not None else None
            if user_store is None:
                user_store = Store.objects.order_by("pk").first()
            if user_store is None:
                raise serializers.ValidationError(
                    {
                        "store": "Нет магазина в системе. Создайте магазин или передайте store в запросе."
                    }
                )
            validated_data["store"] = user_store

        with transaction.atomic():
            batch = ProductBatch.objects.create(**validated_data)
            # reconcile_for_product вызывается из сигнала stock_item_saved при обновлении склада
        return batch


class SupplyOrderItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplyOrderItem
        fields = ("product", "quantity", "purchase_price")

    def validate_quantity(self, value: int) -> int:
        if value < 1:
            raise serializers.ValidationError("Количество должно быть не меньше 1.")
        return value

    def validate_purchase_price(self, value: Decimal) -> Decimal:
        if value < 0:
            raise serializers.ValidationError("Цена закупки не может быть отрицательной.")
        return value


class SupplyOrderItemReadSerializer(serializers.ModelSerializer):
    product_detail = ProductBriefSerializer(source="product", read_only=True)

    class Meta:
        model = SupplyOrderItem
        fields = (
            "id",
            "product",
            "product_detail",
            "quantity",
            "actual_quantity",
            "purchase_price",
            "discrepancy_note",
        )


class ReceivingTaskBriefSerializer(serializers.ModelSerializer):
    assigned_to_username = serializers.SerializerMethodField()

    class Meta:
        model = SupplyReceivingTask
        fields = (
            "id",
            "status",
            "assigned_to",
            "assigned_to_username",
            "created_at",
            "completed_at",
        )

    def get_assigned_to_username(self, obj: SupplyReceivingTask) -> str | None:
        if obj.assigned_to_id is None:
            return None
        return obj.assigned_to.username


class SupplyOrderListSerializer(serializers.ModelSerializer):
    items = SupplyOrderItemReadSerializer(many=True, read_only=True)
    supplier_detail = SupplierSerializer(source="supplier", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    created_by_username = serializers.SerializerMethodField()
    receiving_task = ReceivingTaskBriefSerializer(read_only=True)

    class Meta:
        model = SupplyOrder
        fields = (
            "id",
            "company",
            "store",
            "store_name",
            "supplier",
            "supplier_detail",
            "status",
            "created_at",
            "received_at",
            "total_amount",
            "total_cost",
            "has_discrepancies",
            "planned_receiving_date",
            "created_by",
            "created_by_username",
            "received_by",
            "receiving_task",
            "items",
        )

    def get_created_by_username(self, obj: SupplyOrder) -> str | None:
        if obj.created_by_id is None:
            return None
        return obj.created_by.username


class SupplyOrderCreateSerializer(serializers.ModelSerializer):
    items = SupplyOrderItemWriteSerializer(many=True)
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.EMPLOYEE),
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = SupplyOrder
        fields = ("supplier", "status", "items", "assigned_to", "planned_receiving_date")

    def validate_items(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("Добавьте хотя бы одну позицию в заказ.")
        return value

    def validate_status(self, value: str) -> str:
        allowed = {
            SupplyOrder.Status.DRAFT,
            SupplyOrder.Status.ORDERED,
        }
        if value not in allowed:
            raise serializers.ValidationError(
                "При создании допустимы статусы: draft, ordered."
            )
        return value

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        assigned_to = validated_data.pop("assigned_to", None)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None

        company = Company.objects.order_by("pk").first()
        if company is None:
            raise serializers.ValidationError(
                {"detail": "Нет организации в системе. Создайте Company в админке."}
            )

        store = None
        if user is not None:
            store = getattr(user, "store", None)
        if store is None:
            store = Store.objects.order_by("pk").first()
        if store is None:
            raise serializers.ValidationError(
                {"detail": "Нет магазина в системе. Создайте магазин или привяжите store к пользователю."}
            )

        total_amount = Decimal("0")
        for row in items_data:
            total_amount += Decimal(row["quantity"]) * row["purchase_price"]

        with transaction.atomic():
            order = SupplyOrder.objects.create(
                company=company,
                store=store,
                supplier=validated_data.get("supplier"),
                status=validated_data.get("status", SupplyOrder.Status.DRAFT),
                total_amount=total_amount,
                planned_receiving_date=validated_data.get("planned_receiving_date"),
                created_by=user if user and user.is_authenticated else None,
            )
            for row in items_data:
                SupplyOrderItem.objects.create(order=order, **row)

        if order.status == SupplyOrder.Status.ORDERED:
            from .supply_receiving_service import create_receiving_task

            create_receiving_task(order, user, assigned_to=assigned_to)

        return order


class ReceivingCompleteLineSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    expiration_date = serializers.DateField()
    actual_quantity = serializers.IntegerField(min_value=0)
    discrepancy_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        order_item = SupplyOrderItem.objects.filter(pk=attrs["item_id"]).first()
        if order_item is None:
            return attrs
        actual = attrs["actual_quantity"]
        if actual != order_item.quantity and not (attrs.get("discrepancy_note") or "").strip():
            raise serializers.ValidationError(
                {"discrepancy_note": "Обязательно при расхождении с заказанным количеством."}
            )
        return attrs


class ReceivingCompleteSerializer(serializers.Serializer):
    lines = ReceivingCompleteLineSerializer(many=True)


class SupplyReceivingTaskReadSerializer(serializers.ModelSerializer):
    supply_order = SupplyOrderListSerializer(read_only=True)
    assigned_to_username = serializers.SerializerMethodField()

    class Meta:
        model = SupplyReceivingTask
        fields = (
            "id",
            "status",
            "supply_order",
            "assigned_to",
            "assigned_to_username",
            "created_at",
            "completed_at",
        )

    def get_assigned_to_username(self, obj: SupplyReceivingTask) -> str | None:
        if obj.assigned_to_id is None:
            return None
        return obj.assigned_to.username


class SupplyOrderUpdateSerializer(serializers.ModelSerializer):
    items = SupplyOrderItemWriteSerializer(many=True)

    class Meta:
        model = SupplyOrder
        fields = ("supplier", "items", "planned_receiving_date")

    def validate_items(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("Добавьте хотя бы одну позицию в заказ.")
        return value

    def validate(self, attrs):
        if self.instance.status != SupplyOrder.Status.DRAFT:
            raise serializers.ValidationError(
                {"detail": "Редактировать можно только заказ в статусе «Черновик»."}
            )
        return attrs

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        with transaction.atomic():
            if "supplier" in validated_data:
                instance.supplier = validated_data["supplier"]
            if "planned_receiving_date" in validated_data:
                instance.planned_receiving_date = validated_data["planned_receiving_date"]
            if items_data is not None:
                total_amount = Decimal("0")
                for row in items_data:
                    total_amount += Decimal(row["quantity"]) * row["purchase_price"]
                instance.total_amount = total_amount
                instance.items.all().delete()
                for row in items_data:
                    SupplyOrderItem.objects.create(order=instance, **row)
            instance.save()
        return instance


class SupplyOrderSerializer(serializers.ModelSerializer):
    """Совместимость: полный ответ после receive и legacy."""

    items = SupplyOrderItemReadSerializer(many=True, read_only=True)
    supplier_detail = SupplierSerializer(source="supplier", read_only=True)

    class Meta:
        model = SupplyOrder
        fields = "__all__"


class ShelfSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shelf
        fields = "__all__"


class EquipmentSerializer(serializers.ModelSerializer):
    shelves = ShelfSerializer(many=True, read_only=True)
    slots = EquipmentSlotSerializer(many=True, read_only=True)

    class Meta:
        model = Equipment
        fields = "__all__"

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        if instance is None:
            return attrs

        from .equipment_layout_sync import (
            LAYOUT_CHANGE_BLOCKED_MSG,
            equipment_has_blocking_stock_or_tasks,
            layout_fields_changed,
        )

        new_type = attrs.get("type", instance.type)
        new_rows = attrs.get("rows_count", instance.rows_count)
        if layout_fields_changed(instance, new_type=new_type, new_rows_count=new_rows):
            if equipment_has_blocking_stock_or_tasks(instance):
                raise serializers.ValidationError(LAYOUT_CHANGE_BLOCKED_MSG)
        return attrs

    def update(self, instance, validated_data):
        from .equipment_layout_sync import layout_fields_changed, resync_equipment_layout

        new_type = validated_data.get("type", instance.type)
        new_rows = validated_data.get("rows_count", instance.rows_count)
        should_resync = layout_fields_changed(
            instance,
            new_type=new_type,
            new_rows_count=new_rows,
        )

        instance = super().update(instance, validated_data)
        if should_resync:
            resync_equipment_layout(instance)
        return instance


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "role")


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["username"] = user.username
        token["user_id"] = user.id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Кастомные поля должны попасть и в access — иначе фронт не сможет прочитать роль из access JWT
        refresh = self.get_token(self.user)
        access = refresh.access_token
        access["role"] = self.user.role
        access["username"] = self.user.username
        access["user_id"] = self.user.id
        data["access"] = str(access)
        data["refresh"] = str(refresh)
        return data


class StoreMapSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreMap
        fields = ("id", "store", "width_m", "length_m")


class ZoneSerializer(serializers.ModelSerializer):
    equipment = EquipmentSerializer(many=True, read_only=True)

    class Meta:
        model = Zone
        fields = ("id", "name", "store", "color", "equipment")


class ShelfBriefSerializer(serializers.ModelSerializer):
    """Краткое описание полки для вложения в остатки."""

    class Meta:
        model = Shelf
        fields = ("id", "level", "width", "height", "depth")


class RackBriefSerializer(serializers.ModelSerializer):
    """Краткое описание стеллажа/оборудования плана зала."""

    class Meta:
        model = Equipment
        fields = ("id", "name", "type", "pos_x", "pos_y")


class InventorySerializer(serializers.ModelSerializer):
    shelf_info = ShelfBriefSerializer(source="shelf", read_only=True, allow_null=True)
    rack_info = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = "__all__"

    def get_rack_info(self, obj: Inventory):
        if obj.shelf_id is None:
            return None
        return RackBriefSerializer(obj.shelf.equipment).data


class StaffTaskReadSerializer(serializers.ModelSerializer):
    created_by = UserBriefSerializer(read_only=True)
    assigned_to = UserBriefSerializer(read_only=True)
    zone_name = serializers.CharField(source="zone.name", read_only=True, allow_null=True)

    class Meta:
        model = StaffTask
        fields = (
            "id",
            "title",
            "description",
            "status",
            "created_by",
            "assigned_to",
            "zone",
            "zone_name",
            "equipment",
            "slot",
            "requires_photo",
            "photo_url",
            "created_at",
            "completed_at",
        )
        read_only_fields = (
            "id",
            "status",
            "created_by",
            "photo_url",
            "created_at",
            "completed_at",
        )


class StaffTaskWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffTask
        fields = (
            "title",
            "description",
            "assigned_to",
            "zone",
            "equipment",
            "slot",
            "requires_photo",
        )

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите заголовок поручения.")
        return value


class StaffTaskAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffTask
        fields = ("status", "assigned_to")

    def validate_status(self, value: str) -> str:
        allowed = {
            StaffTask.Status.CREATED,
            StaffTask.Status.IN_PROGRESS,
            StaffTask.Status.COMPLETED,
            StaffTask.Status.CANCELLED,
        }
        if value not in allowed:
            raise serializers.ValidationError("Недопустимый статус.")
        return value


class ChatMessageSerializer(serializers.ModelSerializer):
    sender = UserBriefSerializer(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ("id", "staff_task", "sender", "text", "image_url", "created_at")
        read_only_fields = ("id", "staff_task", "sender", "image_url", "created_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        image_url = data.get("image_url")
        if image_url and image_url.startswith("/"):
            request = self.context.get("request")
            if request is not None:
                data["image_url"] = request.build_absolute_uri(image_url)
        return data


class ChatMessageCreateSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000, required=False, allow_blank=True)


class SlotQrVerifySerializer(serializers.Serializer):
    qr_token = serializers.UUIDField()
