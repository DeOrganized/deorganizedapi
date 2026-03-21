from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Merch, Order
from .serializers import MerchSerializer, OrderSerializer
from users.permissions import HasPaidSubscription
from payments.decorators import x402_required
from django.conf import settings
from django.shortcuts import get_object_or_404
from communities.mixins import CommunityWriteMixin

class IsCreatorOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == 'creator'

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.creator == request.user

class MerchViewSet(CommunityWriteMixin, viewsets.ModelViewSet):
    community_write_role = 'admin'
    queryset = Merch.objects.filter(is_active=True)
    serializer_class = MerchSerializer
    def get_permissions(self):
        """
        Creators require a paid subscription for management actions.
        Everyone can view merch items (SAFE_METHODS).
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'my_merch']:
            return [permissions.IsAuthenticated(), HasPaidSubscription()]
        return [IsCreatorOrReadOnly()]
    lookup_field = 'slug'

    def get_object(self):
        """Support lookup by slug or numeric ID fallback"""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs.get(self.lookup_field) or self.kwargs.get('pk')
        
        if not lookup_value:
            from django.http import Http404
            raise Http404("No lookup value provided")

        from django.db.models import Q
        if str(lookup_value).isdigit():
            obj = queryset.filter(Q(slug=lookup_value) | Q(pk=int(lookup_value))).first()
        else:
            obj = queryset.filter(slug=lookup_value).first()
            
        if obj is None:
            from django.http import Http404
            raise Http404("Merch item not found")
            
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)

    @action(detail=False, methods=['get'])
    def my_merch(self, request):
        if request.user.role != 'creator':
            return Response({"error": "Only creators can view their specific merch management list."}, status=status.HTTP_403_FORBIDDEN)
        merch = Merch.objects.filter(creator=request.user)
        serializer = self.get_serializer(merch, many=True)
        return Response(serializer.data)

class OrderViewSet(viewsets.ModelViewSet):
    """
    Gated order creation with x402 loop.
    """
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'creator':
            # Creators see orders for their merch
            return Order.objects.filter(merch__creator=user)
        # Regular users see their own orders
        return Order.objects.filter(user=user)

    def create(self, request, *args, **kwargs):
        merch_id = request.data.get('merch')
        if not merch_id:
            return Response({"detail": "merch ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        merch_item = get_object_or_404(Merch, id=merch_id)
        
        def get_pay_to(req, **kw):
            return merch_item.creator.stacks_address or getattr(settings, 'PLATFORM_WALLET_ADDRESS', 'SP...')
            
        def get_amounts(req, **kw):
            # Convert from human-readable to micro-units (STX, USDCx, sBTC)
            sbtc_per_usdcx = 0.000015
            return (
                int(float(merch_item.price_stx) * 1_000_000),
                int(float(merch_item.price_usdcx) * 1_000_000),
                int(float(merch_item.price_usdcx) * sbtc_per_usdcx * 100_000_000),
            )

        @x402_required(get_pay_to, get_amounts, description=f"Purchase Merch: {merch_item.name}", bypass_cache=True)
        def gated_create(req, *a, **kw):
            return super(OrderViewSet, self).create(req, *a, **kw)
            
        return gated_create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            buyer_note=self.request.data.get('buyer_note', ''),
            shipping_address=self.request.data.get('shipping_address', ''),
            tx_id=getattr(self.request, 'x402_tx_id', ''),
        )

    @action(detail=False, methods=['get'], url_path='mine')
    def mine(self, request):
        """GET /api/orders/mine/ — orders for creator's merch products."""
        if request.user.role != 'creator':
            return Response({"error": "Only creators can view merch orders."}, status=status.HTTP_403_FORBIDDEN)
        orders = Order.objects.filter(merch__creator=request.user).select_related('merch', 'user').order_by('-created_at')
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        """PATCH /api/orders/{id}/update-status/ — creator updates order status."""
        order = self.get_object()
        if order.merch.creator != request.user:
            return Response({"error": "Not your order to update."}, status=status.HTTP_403_FORBIDDEN)
        new_status = request.data.get('status')
        valid_statuses = [s[0] for s in Order.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response({"error": f"Invalid status. Choose from: {valid_statuses}"}, status=status.HTTP_400_BAD_REQUEST)
        order.status = new_status
        order.save()
        serializer = self.get_serializer(order)
        return Response(serializer.data)
