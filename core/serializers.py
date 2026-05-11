from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Equipment,
    Inventory,
    Product,
    ProductBatch,
    Shelf,
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
