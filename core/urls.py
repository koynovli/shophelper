from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenObtainPairView

from .views import (
    EquipmentViewSet,
    InventoryViewSet,
    PlanogramViewSet,
    PlacementTaskViewSet,
    ProductBatchViewSet,
    ProductViewSet,
    ScanCodeView,
    ShelfViewSet,
    StockItemViewSet,
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
router.register(r"products", ProductViewSet, basename="product")
router.register(r"placement-tasks", PlacementTaskViewSet, basename="placementtask")
router.register(r"planograms", PlanogramViewSet, basename="planogram")
router.register(r"stock-items", StockItemViewSet, basename="stockitem")

urlpatterns = [
    path(
        "token/",
        TokenObtainPairView.as_view(
            serializer_class=CustomTokenObtainPairSerializer,
            permission_classes=[AllowAny],
        ),
        name="token_obtain_pair",
    ),
    path(
        "token/refresh/",
        TokenRefreshView.as_view(permission_classes=[AllowAny]),
        name="token_refresh",
    ),
    path("scan/", ScanCodeView.as_view(), name="scan-code"),
    path("", include(router.urls)),
]
