from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter
from .views import CommunityViewSet, MembershipViewSet

router = DefaultRouter()
router.register(r'communities', CommunityViewSet, basename='community')

communities_router = NestedDefaultRouter(router, r'communities', lookup='community')
communities_router.register(r'members', MembershipViewSet, basename='community-members')

urlpatterns = router.urls + communities_router.urls
