from rest_framework import routers
from shows.views import ShowViewSet, ShowEpisodeViewSet, TagViewSet, GuestRequestViewSet
from news.views import NewsViewSet
from events.views import EventViewSet
from users.views import UserViewSet, LikeViewSet, CommentViewSet, FollowViewSet, NotificationViewSet
from users.wallet_auth import WalletAuthViewSet
from api.views import FeedbackViewSet


router = routers.DefaultRouter()

# Register all ViewSets
router.register(r'shows', ShowViewSet, basename='show')
router.register(r'episodes', ShowEpisodeViewSet, basename='episode')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'guest-requests', GuestRequestViewSet, basename='guest-request')
router.register(r'news', NewsViewSet, basename='news')
router.register(r'events', EventViewSet, basename='event')
router.register(r'users', UserViewSet, basename='user')
router.register(r'likes', LikeViewSet, basename='like')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'follows', FollowViewSet, basename='follow')
router.register(r'notifications', NotificationViewSet, basename='notification')

# Feedback
router.register(r'feedback', FeedbackViewSet, basename='feedback')

# Wallet Authentication
router.register(r'auth/wallet', WalletAuthViewSet, basename='wallet-auth')

urlpatterns = router.urls