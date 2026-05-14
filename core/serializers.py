from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Equipment,
    EquipmentSlot,
    Inventory,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    StockItem,
    Store,
    Supplier,
    SupplyOrder,
    SupplyOrderItem,
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


class EquipmentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Equipment
        fields = ("id", "name")


class EquipmentSlotSerializer(serializers.ModelSerializer):
    planogram = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentSlot
        fields = ("id", "row_index", "col_index", "width_percent", "planogram")

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
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        ).aggregate(total=Sum("quantity"))["total"]
        pending_qty = int(pending_sum or 0)
        target = int(planogram.target_quantity)
        gap = max(0, target - completed_qty - pending_qty)
        status = "OK"
        if pending_qty > 0:
            status = "IN_PROGRESS"
        elif gap > 0:
            status = "DEFICIT" if stock_qty < gap else "IN_PROGRESS"
        return {
            "id": planogram.pk,
            "product": ProductBriefSerializer(planogram.product).data,
            "target_quantity": planogram.target_quantity,
            "stock_quantity": stock_qty,
            "pending_quantity": pending_qty,
            "replenishment_status": status,
        }


class PlacementTaskReadSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    equipment = EquipmentBriefSerializer(read_only=True)
    slot_info = serializers.SerializerMethodField()
    destination_text = serializers.SerializerMethodField()

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
            "created_at",
        )

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
        if value != PlacementTask.Status.COMPLETED:
            raise serializers.ValidationError(
                "Допустимо только завершение задачи: статус COMPLETED."
            )
        return value

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
            PlacementTask.Status.PENDING,
            PlacementTask.Status.IN_PROGRESS,
            PlacementTask.Status.COMPLETED,
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

    class Meta:
        model = Planogram
        fields = ("id", "slot", "product", "target_quantity", "stock_quantity")

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
        if value < 1:
            raise serializers.ValidationError("Целевое количество должно быть не меньше 1.")
        return value


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


class SupplyOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplyOrderItem
        fields = "__all__"


class SupplyOrderSerializer(serializers.ModelSerializer):
    items = SupplyOrderItemSerializer(many=True, read_only=True)
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
