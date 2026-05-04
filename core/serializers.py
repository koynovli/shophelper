from rest_framework import serializers

from .models import (
    Equipment,
    Inventory,
    Product,
    ProductBatch,
    Shelf,
    Supplier,
    SupplyOrder,
    SupplyOrderItem,
    Zone,
)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"


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
