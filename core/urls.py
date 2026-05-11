from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenObtainPairView

from .views import (
    EquipmentViewSet,
    InventoryViewSet,
    ProductBatchViewSet,
    ScanCodeView,
    ShelfViewSet,
    SupplyOrderViewSet,
    ZoneViewSet,
)
from .serializers import CustomTokenObtainPairSerializer

router = DefaultRouter()
router.register(r"supply-orders", SupplyOrderViewSet, basename="supplyorder")
router.register(r"batches", ProductBatchViewSet, basename="productbatch")
router.register(r"zones", ZoneViewSet, basename="zone")
router.register(r"floor-equipment", EquipmentViewSet, basename="floorequipment")
router.register(r"shelves", ShelfViewSet, basename="shelf")
router.register(r"inventory", InventoryViewSet, basename="inventory")

urlpatterns = [
    path("token/", TokenObtainPairView.as_view(serializer_class=CustomTokenObtainPairSerializer), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("scan/", ScanCodeView.as_view(), name="scan-code"),
    path("", include(router.urls)),
]
