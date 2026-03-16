from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MerchViewSet, OrderViewSet

router = DefaultRouter()
router.register(r'merch', MerchViewSet)
router.register(r'orders', OrderViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
