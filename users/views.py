from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.core.cache import cache
import uuid
import time
from .models import Like, Comment, Follow, Notification, RTMPDestination, Subscription, CreatorPlaylist
from .serializers import (
    UserSerializer, UserListSerializer, UserRegistrationSerializer,
    UserUpdateSerializer,
    LikeSerializer, CommentSerializer, CommentCreateSerializer,
    FollowSerializer, CreatorProfileSerializer,
    WalletLoginOrCheckSerializer, CompleteSetupSerializer,
    NotificationSerializer, RTMPDestinationSerializer,
    BroadcastScheduleSerializer, SubscriptionSerializer
)

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User model and authentication.
    
    List: GET /api/users/
    Create (Register): POST /api/users/register/
    Retrieve: GET /api/users/{id}/
    Update: PUT/PATCH /api/users/{id}/ (owner only)
    
    Auth actions:
    - register: POST /api/users/register/
    - login: POST /api/users/login/
    - me: GET /api/users/me/
    """
    queryset = User.objects.all()
    # Note: follower_count and following_count are provided by @property methods in the User model
    # No need to annotate here as it would conflict with the properties
    permission_classes = []  # Override global defaults, use get_permissions() instead
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name']
    ordering_fields = ['date_joined']  # Removed 'follower_count' since it's not an annotated field
    ordering = ['-date_joined']
    
    def get_serializer_class(self):
        if self.action == 'register':
            return UserRegistrationSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        elif self.action == 'list':
            return UserListSerializer
        elif self.action == 'creator_profile':
            return CreatorProfileSerializer
        return UserSerializer
    
    def get_serializer(self, *args, **kwargs):
        """Inject request context for proper image URL generation"""
        kwargs.setdefault('context', self.get_serializer_context())
        return super().get_serializer(*args, **kwargs)
    
    def get_permissions(self):
        if self.action in ['register', 'login', 'wallet_login_or_check', 'complete_setup']:
            return [AllowAny()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return super().get_permissions()
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by role
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        
        # Filter by verified status
        is_verified = self.request.query_params.get('is_verified')
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified.lower() == 'true')
        
        return queryset
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        """Register a new user"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def login(self, request):
        """Login user with username/email and password"""
        from django.contrib.auth import authenticate
        
        username_or_email = request.data.get('username')
        password = request.data.get('password')
        
        if not username_or_email or not password:
            return Response(
                {'error': 'Please provide both username/email and password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to authenticate with username or email
        user = authenticate(username=username_or_email, password=password)
        
        if not user:
            # Try with email
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        
        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            })
        
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get current user's profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def creator_profile(self, request, pk=None):
        """Get detailed creator profile"""
        user = self.get_object()
        if user.role != 'creator':
            return Response(
                {'error': 'This user is not a creator'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = CreatorProfileSerializer(user)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get aggregate stats for a creator"""
        from shows.models import Show
        from events.models import Event
        
        user = self.get_object()
        
        # Aggregate counts
        shows = Show.objects.filter(creator=user)
        events = Event.objects.filter(organizer=user)
        
        # Engagement stats
        # Assuming shows have likes/comments relation or using ContentType
        total_likes = 0
        total_comments = 0
        total_views = 0
        total_shares = 0
        
        for show in shows:
            total_likes += show.likes.count()
            total_comments += show.comments.count()
            total_views += getattr(show, 'views_count', 0)
            total_shares += getattr(show, 'share_count', 0)
            
        return Response({
            'total_views': total_views,
            'total_shares': total_shares,
            'total_likes': total_likes,
            'total_comments': total_comments,
            'follower_count': user.follower_count,
            'following_count': user.following_count,
            'show_count': shows.count(),
            'event_count': events.count(),
        })

    @action(detail=False, methods=['get'], url_path='by-username/(?P<username>[^/.]+)')
    def fetch_by_username(self, request, username=None):
        """Fetch user profile by username"""
        from django.shortcuts import get_object_or_404
        user = get_object_or_404(User, username=username)
        serializer = self.get_serializer(user)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def liked_shows(self, request, pk=None):
        """Get shows liked by this user"""
        user = self.get_object()
        # Import Show model here to avoid circular imports
        from shows.models import Show
        from django.contrib.contenttypes.models import ContentType
        
        # Get Show ContentType
        show_content_type = ContentType.objects.get_for_model(Show)
        
        # Get likes for shows
        liked_show_ids = user.likes.filter(
            content_type=show_content_type
        ).values_list('object_id', flat=True)
        
        # Get the actual shows
        shows = Show.objects.filter(id__in=liked_show_ids)
        
        # Import ShowSerializer
        from shows.serializers import ShowSerializer
        serializer = ShowSerializer(shows, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def following(self, request, pk=None):
        """Get users that this user is following"""
        user = self.get_object()
        # Get all Follow objects where this user is the follower
        following_users = User.objects.filter(
            followers__follower=user
        ).distinct()
        
        serializer = UserSerializer(following_users, many=True, context={'request': request})
        return Response(serializer.data)
    
    # ============================================
    # WALLET AUTHENTICATION ENDPOINTS (DEFERRED USER CREATION)
    # ============================================
    # ⚠️ WARNING: These endpoints DO NOT verify wallet signatures
    # This is acceptable for MVP/testing but MUST be replaced before production
    # See IMPLEMENTATION_ISSUES_ANALYSIS.md for security implications
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny], url_path='wallet-login-or-check')
    def wallet_login_or_check(self, request):
        """
        Check if wallet exists and login if it does.
        Returns is_new=true if wallet doesn't exist.
        
        POST /api/users/wallet-login-or-check/
        Body: { "wallet_address": "SP..." }
        
        Returns (existing user): {
            "is_new": false,
            "user": {...},
            "tokens": {
                "access": "...",
                "refresh": "..."
            }
        }
        
        Returns (new user): {
            "is_new": true
        }
        """
        import logging
        logger = logging.getLogger(__name__)
        
        serializer = WalletLoginOrCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        wallet_address = serializer.validated_data['wallet_address']
        logger.info(f"Wallet login check for address: {wallet_address}")
        
        # Check if user exists
        try:
            user = User.objects.get(stacks_address=wallet_address)
            logger.info(f"Existing user found: {user.username}")
            
            # User exists - issue JWT (standardized token order)
            refresh = RefreshToken.for_user(user)
            return Response({
                'is_new': False,
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                }
            })
            
        except User.DoesNotExist:
            logger.info(f"New wallet detected: {wallet_address}")
            # New user - return flag only
            return Response({'is_new': True})
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny], url_path='complete-setup')
    def complete_setup(self, request):
        """
        Complete user setup and create account.
        This is called after user fills out the setup form on frontend.
        
        POST /api/users/complete-setup/
        Body: {
            "wallet_address": "SP...",
            "username": "optional",
            "role": "user | creator",
            "bio": "...",
            "website": "...",
            etc.
        }
        
        Returns: {
            "user": {...},
            "tokens": {
                "access": "...",
                "refresh": "..."
            }
        }
        """
        import logging
        from django.db import IntegrityError, transaction
        logger = logging.getLogger(__name__)
        
        # Debug: log incoming request
        logger.info(f"📥 Complete setup request: {request.data}")
        
        serializer = CompleteSetupSerializer(data=request.data)
        
        # Debug: check validation
        if not serializer.is_valid():
            logger.error(f"❌ Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"✅ Validation passed")
        
        wallet_address = serializer.validated_data['wallet_address']
        
        # CRITICAL FIX #5: Check if wallet already registered
        if User.objects.filter(stacks_address=wallet_address).exists():
            logger.warning(f"Duplicate registration attempt for wallet: {wallet_address}")
            return Response(
                {
                    'error': 'Wallet address already registered',
                    'detail': 'This wallet is already associated with an account. Use wallet-login-or-check to login.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate username if not provided
        username = serializer.validated_data.get('username')
        if not username:
            # Auto-generate from wallet address
            base_username = f'user_{wallet_address[:8]}'
            username = base_username
            counter = 1
            # CRITICAL FIX #3: Race condition protection with max retries
            max_retries = 10
            while counter < max_retries:
                if not User.objects.filter(username=username).exists():
                    break
                username = f'{base_username}_{counter}'
                counter += 1
            else:
                # Fallback to UUID if all retries failed
                import uuid
                username = f'user_{uuid.uuid4().hex[:8]}'
        
        # CRITICAL FIX #7: Create user with unusable password
        # Wrap in transaction for atomicity
        try:
            with transaction.atomic():
                user = User.objects.create(
                    stacks_address=wallet_address,
                    username=username,
                    display_name=serializer.validated_data.get('display_name', ''),
                    role=serializer.validated_data.get('role', 'user'),
                    first_name=serializer.validated_data.get('first_name', ''),
                    last_name=serializer.validated_data.get('last_name', ''),
                    bio=serializer.validated_data.get('bio', ''),
                    website=serializer.validated_data.get('website', ''),
                    twitter=serializer.validated_data.get('twitter', ''),
                    instagram=serializer.validated_data.get('instagram', ''),
                    youtube=serializer.validated_data.get('youtube', '')
                )
                # Set unusable password for wallet-only users
                user.set_unusable_password()
                user.save()
                
                logger.info(f"New user created: {user.username} with wallet {wallet_address}")
                
        except IntegrityError as e:
            logger.error(f"User creation failed: {str(e)}")
            return Response(
                {
                    'error': 'User creation failed',
                    'detail': 'Username or wallet address already exists. Please try again.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Issue JWT tokens (standardized order: access then refresh)
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': UserSerializer(user).data,
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        }, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        """Update user profile - only allow users to update their own profile"""
        instance = self.get_object()
        
        # Check if user is updating their own profile
        if instance.id != request.user.id:
            return Response(
                {'error': 'You can only update your own profile'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response(UserSerializer(instance).data)
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update user profile"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get current authenticated user's profile"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # ============================================
    # ADMIN DASHBOARD ENDPOINTS (Staff only)
    # ============================================

    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser], url_path='admin-stats')
    def admin_stats(self, request):
        """
        Get platform overview stats for admin dashboard.
        GET /api/users/admin-stats/
        Staff only.
        """
        from django.utils import timezone
        from datetime import timedelta
        from shows.models import Show
        from news.models import News
        from events.models import Event
        from api.models import Feedback

        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        seven_days_ago = now - timedelta(days=7)

        # Core counts
        total_users = User.objects.count()
        total_creators = User.objects.filter(role='creator').count()
        total_regular_users = User.objects.filter(role='user').count()
        total_shows = Show.objects.count()
        total_events = Event.objects.count()
        total_news = News.objects.count()

        # Recent activity
        new_users_7d = User.objects.filter(date_joined__gte=seven_days_ago).count()
        new_users_30d = User.objects.filter(date_joined__gte=thirty_days_ago).count()

        # Engagement
        total_likes = Like.objects.count()
        total_comments = Comment.objects.count()
        total_follows = Follow.objects.count()

        # Feedback
        total_feedback = Feedback.objects.count()
        unresolved_feedback = Feedback.objects.filter(resolved=False).count()

        # Recent signups (last 10)
        recent_users = User.objects.order_by('-date_joined')[:10]
        recent_users_data = UserListSerializer(recent_users, many=True, context={'request': request}).data

        return Response({
            'overview': {
                'total_users': total_users,
                'total_creators': total_creators,
                'total_regular_users': total_regular_users,
                'total_shows': total_shows,
                'total_events': total_events,
                'total_news': total_news,
            },
            'activity': {
                'new_users_7d': new_users_7d,
                'new_users_30d': new_users_30d,
                'total_likes': total_likes,
                'total_comments': total_comments,
                'total_follows': total_follows,
            },
            'feedback': {
                'total': total_feedback,
                'unresolved': unresolved_feedback,
            },
            'recent_users': recent_users_data,
        })

    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser], url_path='admin-users')
    def admin_users(self, request):
        """
        Get all users for admin management.
        GET /api/users/admin-users/?search=&role=&page=
        Staff only.
        """
        queryset = User.objects.all().order_by('-date_joined')

        # Filters
        role = request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(username__icontains=search)

        is_verified = request.query_params.get('is_verified')
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified.lower() == 'true')

        # Paginate
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = UserListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser], url_path='toggle-verification')
    def admin_toggle_verification(self, request, pk=None):
        """
        Toggle user verification status.
        POST /api/users/{id}/toggle-verification/
        Staff only.
        """
        user = self.get_object()
        user.is_verified = not user.is_verified
        user.save(update_fields=['is_verified'])
        return Response({
            'id': user.id,
            'username': user.username,
            'is_verified': user.is_verified,
            'message': f'User {"verified" if user.is_verified else "unverified"} successfully'
        })


class LikeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Like model.
    
    List: GET /api/likes/
    Create: POST /api/likes/
    Delete: DELETE /api/likes/{id}/
    
    Custom actions:
    - toggle: POST /api/likes/toggle/
    """
    queryset = Like.objects.select_related('user')
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by content type and object
        content_type_id = self.request.query_params.get('content_type')
        object_id = self.request.query_params.get('object_id')
        
        if content_type_id and object_id:
            queryset = queryset.filter(
                content_type_id=content_type_id,
                object_id=object_id
            )
        
        # Filter by user
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def content_types(self, request):
        """Get mapping of model names to ContentType IDs"""
        from django.contrib.contenttypes.models import ContentType
        from shows.models import Show
        from posts.models import Post
        from news.models import News
        from events.models import Event
        
        models = [Show, Post, News, Event]
        result = []
        for model in models:
            ct = ContentType.objects.get_for_model(model)
            result.append({
                'model': model.__name__.lower(),
                'id': ct.id
            })
            
        return Response(result)
    
    @action(detail=False, methods=['post'])
    def toggle(self, request):
        """Toggle like on content (like if not liked, unlike if already liked)"""
        from django.contrib.contenttypes.models import ContentType
        
        content_type_id = request.data.get('content_type')
        object_id = request.data.get('object_id')
        
        if not content_type_id or not object_id:
            return Response(
                {'error': 'content_type and object_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Robustness: Verify ContentType exists
        try:
            ct = ContentType.objects.get(pk=content_type_id)
        except ContentType.DoesNotExist:
            return Response(
                {'error': f'Invalid content_type_id: {content_type_id}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Robustness: Verify target object exists
        model_class = ct.model_class()
        if not model_class.objects.filter(pk=object_id).exists():
             return Response(
                {'error': f'Target object {object_id} for {ct.model} does not exist'},
                status=status.HTTP_404_NOT_FOUND
            )

        like, created = Like.objects.get_or_create(
            user=request.user,
            content_type=ct,
            object_id=object_id
        )
        
        if not created:
            like.delete()
            return Response({'status': 'unliked'}, status=status.HTTP_200_OK)
        
        # Notification is automatically created by signal handler
        # (see users/signals.py - create_like_notification)
        
        return Response(
            {'status': 'liked', 'like': LikeSerializer(like).data},
            status=status.HTTP_201_CREATED
        )


class CommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Comment model with nested reply support.
    
    List: GET /api/comments/
    Create: POST /api/comments/
    Retrieve: GET /api/comments/{id}/
    Update: PUT/PATCH /api/comments/{id}/ (owner only)
    Delete: DELETE /api/comments/{id}/ (owner only)
    """
    queryset = Comment.objects.select_related('user')
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CommentCreateSerializer
        return CommentSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by content type and object
        content_type_id = self.request.query_params.get('content_type')
        object_id = self.request.query_params.get('object_id')
        
        if content_type_id and object_id:
            queryset = queryset.filter(
                content_type_id=content_type_id,
                object_id=object_id
            )
        
        # Filter by parent (top-level comments only)
        if self.request.query_params.get('top_level') == 'true':
            queryset = queryset.filter(parent__isnull=True)
        
        return queryset
    
    def perform_create(self, serializer):
        # Save comment - notification is automatically created by signal handler
        # (see users/signals.py - create_comment_notification)
        comment = serializer.save(user=self.request.user)


class FollowViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Follow model.
    
    List: GET /api/follows/
    Create: POST /api/follows/
    Delete: DELETE /api/follows/{id}/
    
    Custom actions:
    - toggle: POST /api/follows/toggle/
    - followers: GET /api/follows/followers/{user_id}/
    - following: GET /api/follows/following/{user_id}/
    """
    queryset = Follow.objects.select_related('follower', 'following')
    serializer_class = FollowSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by follower
        follower_id = self.request.query_params.get('follower')
        if follower_id:
            queryset = queryset.filter(follower_id=follower_id)
        
        # Filter by following
        following_id = self.request.query_params.get('following')
        if following_id:
            queryset = queryset.filter(following_id=following_id)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(follower=self.request.user)
    
    @action(detail=False, methods=['post'])
    def toggle(self, request):
        """Toggle follow on user (follow if not following, unfollow if already following)"""
        following_id = request.data.get('following_id')
        
        if not following_id:
            return Response(
                {'error': 'following_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if int(following_id) == request.user.id:
            return Response(
                {'error': 'Cannot follow yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            following_id=following_id
        )
        
        if not created:
            follow.delete()
            return Response({'status': 'unfollowed'}, status=status.HTTP_200_OK)
        
        # Create notification for the user being followed
        Notification.objects.create(
            recipient=follow.following,
            actor=request.user,
            notification_type='follow'
        )
        
        return Response(
            {'status': 'followed', 'follow': FollowSerializer(follow).data},
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'])
    def followers(self, request):
        """Get followers of a user"""
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        follows = self.get_queryset().filter(following_id=user_id)
        serializer = self.get_serializer(follows, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def following(self, request):
        """Get users that a user is following"""
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        follows = self.get_queryset().filter(follower_id=user_id)
        serializer = self.get_serializer(follows, many=True)
        return Response(serializer.data)


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user notifications.
    
    List: GET /api/notifications/
    Mark Read: POST /api/notifications/{id}/mark_read/
    Mark All Read: POST /api/notifications/mark_all_read/
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return notifications for the current user, ordered by newest first"""
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related('actor', 'recipient')
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a single notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read for the current user"""
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({
            'status': 'all marked as read',
            'count': count
        })


class RTMPDestinationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for RTMP streaming destinations.
    
    List: GET /api/rtmp-destinations/
    Create: POST /api/rtmp-destinations/
    Retrieve: GET /api/rtmp-destinations/{id}/
    Update: PUT/PATCH /api/rtmp-destinations/{id}/
    Delete: DELETE /api/rtmp-destinations/{id}/
    
    All endpoints are scoped to the authenticated user's destinations only.
    """
    serializer_class = RTMPDestinationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RTMPDestination.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # ------------------------------------------------------------------
    # Broadcast Schedule (on UserViewSet)
    # Access via:  POST /api/users/broadcast-schedule/
    #              GET  /api/users/broadcast-schedule/
    # ------------------------------------------------------------------


class BroadcastScheduleViewSet(viewsets.ViewSet):
    """
    GET  /api/broadcast-schedule/ — return current user's broadcast schedule
    POST /api/broadcast-schedule/ — update broadcast schedule
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        user = request.user
        return Response({
            'broadcast_time': str(user.broadcast_time) if user.broadcast_time else None,
            'broadcast_days': user.broadcast_days or [],
            'broadcast_timezone': user.broadcast_timezone or 'UTC',
        })

    def create(self, request):
        serializer = BroadcastScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        data = serializer.validated_data
        if 'broadcast_time' in data:
            user.broadcast_time = data['broadcast_time']
        if 'broadcast_days' in data:
            user.broadcast_days = data['broadcast_days']
        if 'broadcast_timezone' in data:
            user.broadcast_timezone = data['broadcast_timezone']
        user.save(update_fields=['broadcast_time', 'broadcast_days', 'broadcast_timezone'])

        return Response({
            'broadcast_time': str(user.broadcast_time) if user.broadcast_time else None,
            'broadcast_days': user.broadcast_days or [],
            'broadcast_timezone': user.broadcast_timezone or 'UTC',
        })


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Subscription management.

    GET  /api/subscription/    — returns current user's subscription (auto-creates free tier)
    PATCH /api/subscription/1/ — update subscription (e.g. after STX payment)
    POST /api/subscription/upgrade/ — x402-gated plan upgrade
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    # Plan prices (human-readable, converted to micro in the action)
    PLAN_PRICES = {
        'starter': {'stx': 1, 'usdcx': 1},
        'pro': {'stx': 1, 'usdcx': 1},
        'enterprise': {'stx': 1, 'usdcx': 1},
    }

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        # Auto-create free subscription if none exists
        sub, created = Subscription.objects.get_or_create(
            user=request.user,
            defaults={'plan': 'free', 'status': 'active'}
        )
        serializer = self.get_serializer(sub)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        old_plan = self.get_object().plan
        instance = serializer.save()
        new_plan = instance.plan

        # Auto-create CreatorPlaylist when upgrading from free to a paid plan
        if old_plan == 'free' and new_plan != 'free':
            folder_name = f"creator_{instance.user.id}_{instance.user.username}"
            CreatorPlaylist.objects.get_or_create(
                user=instance.user,
                dcpe_playlist_name=folder_name,
                defaults={
                    'label': f"{instance.user.display_name or instance.user.username}'s Content"
                }
            )

    @action(detail=False, methods=['get'], url_path='plan-prices')
    def plan_prices(self, request):
        """GET /api/subscription/plan-prices/ — returns plan USDCx prices."""
        return Response(self.PLAN_PRICES)

    @action(detail=False, methods=['post'], url_path='upgrade')
    def upgrade(self, request):
        """
        POST /api/subscription/upgrade/
        Body: { "plan": "starter"|"pro"|"enterprise" }
        x402-gated: triggers wallet payment, then upgrades subscription.
        """
        from payments.decorators import x402_required
        from django.conf import settings
        from payments.models import PaymentReceipt

        target_plan = request.data.get('plan', '')
        if target_plan not in self.PLAN_PRICES:
            return Response(
                {"error": f"Invalid plan. Choose from: {list(self.PLAN_PRICES.keys())}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        prices = self.PLAN_PRICES[target_plan]

        def get_pay_to(req, **kw):
            return getattr(settings, 'PLATFORM_WALLET_ADDRESS', 'SP...')

        def get_amounts(req, **kw):
            # Convert to micro-units (STX, USDCx, sBTC)
            # sBTC: 1 USDCx ≈ 0.0000015 BTC → in satoshis (×100_000_000)
            sbtc_per_usdcx = 0.0000015
            return (
                int(prices['stx'] * 1_000_000),
                int(prices['usdcx'] * 1_000_000),
                int(prices['usdcx'] * sbtc_per_usdcx * 100_000_000),
            )

        @x402_required(get_pay_to, get_amounts, description=f"Upgrade to {target_plan.title()} Plan")
        def gated_upgrade(req, *a, **kw):
            # Pass unique resource_id per plan to prevent bypass
            kw['resource_id'] = f"subscription_{target_plan}"
            sub, _ = Subscription.objects.get_or_create(
                user=req.user,
                defaults={'plan': 'free', 'status': 'active'}
            )
            old_plan = sub.plan
            sub.plan = target_plan
            sub.status = 'active'
            sub.save()

            # Auto-create DCPE folder when upgrading from free
            if old_plan == 'free' and target_plan != 'free':
                folder_name = f"creator_{sub.user.id}_{sub.user.username}"
                CreatorPlaylist.objects.get_or_create(
                    user=sub.user,
                    dcpe_playlist_name=folder_name,
                    defaults={
                        'label': f"{sub.user.display_name or sub.user.username}'s Content"
                    }
                )

            serializer = self.get_serializer(sub)
            return Response(serializer.data)

        return gated_upgrade(request, resource_id=f"subscription_{target_plan}")


class TipViewSet(viewsets.ViewSet):
    """
    Endpoints for tipping creators via x402.
    
    GET  /api/tips/<creator_id>/payment-info/ — returns payTo address and creator info
    POST /api/tips/<creator_id>/send/         — x402-gated tip submission
    """
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['get'], url_path='payment-info')
    def payment_info(self, request, pk=None):
        """GET /api/tips/<creator_id>/payment-info/ — returns tip payment details."""
        try:
            creator = User.objects.get(pk=pk, role='creator')
        except User.DoesNotExist:
            return Response({"error": "Creator not found"}, status=status.HTTP_404_NOT_FOUND)

        pay_to = getattr(creator, 'payout_stx_address', '') or creator.stacks_address or ''
        return Response({
            "creator_id": creator.id,
            "creator_username": creator.username,
            "creator_display_name": creator.display_name or creator.username,
            "pay_to": pay_to,
            "profile_picture": creator.profile_picture.url if creator.profile_picture else None,
        })

    @action(detail=True, methods=['post'], url_path='send')
    def send(self, request, pk=None):
        """POST /api/tips/<creator_id>/send/ — x402-gated tip."""
        from payments.decorators import x402_required
        from payments.models import PaymentReceipt

        try:
            creator = User.objects.get(pk=pk, role='creator')
        except User.DoesNotExist:
            return Response({"error": "Creator not found"}, status=status.HTTP_404_NOT_FOUND)

        # Amount comes from the request body (user-chosen)
        amount_stx = int(request.data.get('amount_stx', 0))
        amount_usdcx = int(request.data.get('amount_usdcx', 0))
        amount_sbtc = int(request.data.get('amount_sbtc', 0))

        if amount_stx <= 0 and amount_usdcx <= 0 and amount_sbtc <= 0:
            return Response({"error": "Tip amount must be > 0"}, status=status.HTTP_400_BAD_REQUEST)

        pay_to = getattr(creator, 'payout_stx_address', '') or creator.stacks_address or ''

        def get_pay_to(req, **kw):
            return pay_to

        def get_amounts(req, **kw):
            # Already in micro-units from the frontend
            return amount_stx, amount_usdcx, amount_sbtc

        @x402_required(get_pay_to, get_amounts, description=f"Tip for {creator.display_name or creator.username}", bypass_cache=True)
        def gated_tip(req, *a, **kw):
            return Response({
                "status": "success",
                "message": f"Tip sent to {creator.display_name or creator.username}!",
                "creator_id": creator.id,
                "tx_id": getattr(req, 'x402_tx_id', ''),
            })

        return gated_tip(request)

