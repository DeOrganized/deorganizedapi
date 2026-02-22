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
from .models import Like, Comment, Follow, Notification
from .serializers import (
    UserSerializer, UserListSerializer, UserRegistrationSerializer,
    UserUpdateSerializer,
    LikeSerializer, CommentSerializer, CommentCreateSerializer,
    FollowSerializer, CreatorProfileSerializer,
    WalletLoginOrCheckSerializer, CompleteSetupSerializer,
    NotificationSerializer
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
    
    @action(detail=False, methods=['post'])
    def toggle(self, request):
        """Toggle like on content (like if not liked, unlike if already liked)"""
        content_type_id = request.data.get('content_type')
        object_id = request.data.get('object_id')
        
        if not content_type_id or not object_id:
            return Response(
                {'error': 'content_type and object_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        like, created = Like.objects.get_or_create(
            user=request.user,
            content_type_id=content_type_id,
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

