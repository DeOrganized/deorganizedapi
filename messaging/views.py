from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import Thread, Message
from .serializers import ThreadSerializer, MessageSerializer
from payments.decorators import x402_required
from django.conf import settings

class ThreadViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ThreadSerializer

    def get_queryset(self):
        # Users only see threads they are participating in
        return Thread.objects.filter(participants=self.request.user)

    def create(self, request, *args, **kwargs):
        # Support common direct message creation
        recipient_id = request.data.get('recipient_id')
        if not recipient_id:
            return Response({"detail": "recipient_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if a thread already exists between these two
        existing = Thread.objects.filter(participants=request.user).filter(participants__id=recipient_id)
        if existing.exists():
            return Response(ThreadSerializer(existing.first()).data)
        
        # Create new thread
        thread = Thread.objects.create(is_premium=request.data.get('is_premium', False))
        thread.participants.add(request.user, recipient_id)
        return Response(ThreadSerializer(thread).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        thread = self.get_object()
        
        # Gating logic for premium threads
        if thread.is_premium:
            # Reusable amounts logic for the decorator
            def get_amounts(req, **kwargs):
                sbtc_per_usdcx = 0.000015
                return (
                    thread.price_stx,
                    thread.price_usdcx,
                    int(float(thread.price_usdcx) * sbtc_per_usdcx * 100_000_000),
                )
            
            def get_pay_to(req, **kwargs):
                # Platforms handle messaging fees for now
                return getattr(settings, 'PLATFORM_WALLET_ADDRESS', 'SP...')

            # Wrapper for the actual logic to be used with the decorator manually or via dispatch
            @x402_required(get_pay_to, get_amounts, description=f"Unlock conversation Thread #{thread.id}")
            def get_gated_messages(req, thread_obj):
                messages = thread_obj.messages.all()
                serializer = MessageSerializer(messages, many=True)
                return Response(serializer.data)

            if request.method == 'GET':
                return get_gated_messages(request, thread_obj=thread)

        # Standard non-premium flow or POSTing new messages
        if request.method == 'GET':
            messages = thread.messages.all()
            serializer = MessageSerializer(messages, many=True)
            return Response(serializer.data)
        
        elif request.method == 'POST':
            serializer = MessageSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(thread=thread, sender=request.user)
                thread.save() # Update updated_at
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
