from rest_framework import serializers
from .models import Merch, Order

class MerchSerializer(serializers.ModelSerializer):
    creator_username = serializers.ReadOnlyField(source='creator.username')
    
    class Meta:
        model = Merch
        fields = [
            'id', 'creator', 'creator_username', 'name', 'slug', 
            'description', 'price_stx', 'price_usdcx', 'stock', 
            'image', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'creator', 'slug', 'created_at']

class OrderSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    merch_name = serializers.ReadOnlyField(source='merch.name')
    
    class Meta:
        model = Order
        fields = [
            'id', 'user', 'username', 'merch', 'merch_name', 
            'quantity', 'tx_id', 'payment_currency', 'amount_paid', 
            'status', 'shipping_address', 'buyer_note', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'tx_id', 'amount_paid', 'status']
