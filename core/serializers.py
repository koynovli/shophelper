from rest_framework import serializers

from .models import ProductBatch, Supplier, SupplyOrder, SupplyOrderItem


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
