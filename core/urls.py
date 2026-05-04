from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductBatchViewSet, SupplyOrderViewSet

router = DefaultRouter()
router.register(r"supply-orders", SupplyOrderViewSet, basename="supplyorder")
router.register(r"batches", ProductBatchViewSet, basename="productbatch")

urlpatterns = [
    path("", include(router.urls)),
]
