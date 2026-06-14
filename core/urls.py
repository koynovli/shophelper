from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenObtainPairView

from .product_tracking import (
    ProductTrackingCategoriesView,
    ProductTrackingDetailView,
    ProductTrackingListView,
)
from .views import (
    CategoryViewSet,
    EquipmentSlotAdjustView,
    EquipmentSlotCapacityPreviewView,
    EquipmentViewSet,
    InventoryViewSet,
    PlanogramViewSet,
    PlacementTaskViewSet,
    ProductBatchViewSet,
    ProductViewSet,
    ScanCodeView,
    ScanResolveView,
    ShelfClearingTaskViewSet,
    ShelfViewSet,
    StaffTaskViewSet,
    StockItemViewSet,
    EmployeeListView,
    SupplierViewSet,
    SupplyOrderViewSet,
    SupplyReceivingTaskViewSet,
    StoreMapView,
    TaskPoolView,
    WriteOffTaskViewSet,
    ZoneViewSet,
)
from .serializers import CustomTokenObtainPairSerializer

router = DefaultRouter()
router.register(r"suppliers", SupplierViewSet, basename="supplier")
router.register(r"supply-orders", SupplyOrderViewSet, basename="supplyorder")
router.register(
    r"receiving-tasks", SupplyReceivingTaskViewSet, basename="receivingtask"
)
router.register(r"batches", ProductBatchViewSet, basename="productbatch")
router.register(r"zones", ZoneViewSet, basename="zone")
router.register(r"floor-equipment", EquipmentViewSet, basename="floorequipment")
router.register(r"shelves", ShelfViewSet, basename="shelf")
router.register(r"inventory", InventoryViewSet, basename="inventory")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"products", ProductViewSet, basename="product")
router.register(r"placement-tasks", PlacementTaskViewSet, basename="placementtask")
router.register(
    r"shelf-clearing-tasks", ShelfClearingTaskViewSet, basename="shelfclearingtask"
)
router.register(r"write-off-tasks", WriteOffTaskViewSet, basename="writeofftask")
router.register(r"staff-tasks", StaffTaskViewSet, basename="stafftask")
router.register(r"planograms", PlanogramViewSet, basename="planogram")
router.register(r"stock-items", StockItemViewSet, basename="stockitem")

urlpatterns = [
    path(
        "product-tracking/categories/",
        ProductTrackingCategoriesView.as_view(),
        name="product-tracking-categories",
    ),
    path(
        "product-tracking/<int:pk>/",
        ProductTrackingDetailView.as_view(),
        name="product-tracking-detail",
    ),
    path(
        "product-tracking/",
        ProductTrackingListView.as_view(),
        name="product-tracking-list",
    ),
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
    path("scan/resolve/", ScanResolveView.as_view(), name="scan-resolve"),
    path("store-map/", StoreMapView.as_view(), name="store-map"),
    path("task-pool/", TaskPoolView.as_view(), name="task-pool"),
    path("employees/", EmployeeListView.as_view(), name="employee-list"),
    path(
        "slots/<int:pk>/adjust-qty/",
        EquipmentSlotAdjustView.as_view(),
        name="slot-adjust-qty",
    ),
    path(
        "slots/<int:pk>/capacity-preview/",
        EquipmentSlotCapacityPreviewView.as_view(),
        name="slot-capacity-preview",
    ),
    path("", include(router.urls)),
]
