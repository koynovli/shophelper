from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EquipmentViewSet,
    InventoryViewSet,
    ProductBatchViewSet,
    ShelfViewSet,
    SupplyOrderViewSet,
    ZoneViewSet,
)

router = DefaultRouter()
router.register(r"supply-orders", SupplyOrderViewSet, basename="supplyorder")
router.register(r"batches", ProductBatchViewSet, basename="productbatch")
router.register(r"zones", ZoneViewSet, basename="zone")
router.register(r"floor-equipment", EquipmentViewSet, basename="floorequipment")
router.register(r"shelves", ShelfViewSet, basename="shelf")
router.register(r"inventory", InventoryViewSet, basename="inventory")

urlpatterns = [
    path("", include(router.urls)),
]
