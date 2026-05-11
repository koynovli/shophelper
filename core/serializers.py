from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Equipment,
    Inventory,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    StockItem,
    Supplier,
    SupplyOrder,
    SupplyOrderItem,
    User,
    Zone,
)


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


class PlacementTaskReadSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    equipment = EquipmentBriefSerializer(read_only=True)

    class Meta:
        model = PlacementTask
        fields = ("id", "planogram", "product", "equipment", "quantity", "status", "created_at")


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


class PlanogramReadSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    equipment = EquipmentBriefSerializer(read_only=True)
    stock_quantity = serializers.SerializerMethodField()

    class Meta:
        model = Planogram
        fields = ("id", "equipment", "product", "target_quantity", "stock_quantity")

    def get_stock_quantity(self, obj: Planogram) -> int:
        row = StockItem.objects.filter(product_id=obj.product_id).first()
        return int(row.quantity) if row else 0


class PlanogramWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Planogram
        fields = ("equipment", "product", "target_quantity")

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

    class Meta:
        model = ProductBatch
        fields = "__all__"

    def get_remaining_days(self, obj: ProductBatch) -> int:
        return obj.get_remaining_days()

    def get_is_expired(self, obj: ProductBatch) -> bool:
        return obj.is_expired


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
