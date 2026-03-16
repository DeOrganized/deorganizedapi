from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Thread, Message

User = get_user_model()

class UserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'display_name', 'profile_picture', 'role']

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSimpleSerializer(read_only=True)
    body = serializers.CharField(source='text')
    sent_at = serializers.DateTimeField(source='created_at', read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'thread', 'sender', 'body', 'sent_at', 'is_read']
        read_only_fields = ['sender', 'sent_at', 'thread']

class ThreadSerializer(serializers.ModelSerializer):
    participants = UserSimpleSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.DateTimeField(source='updated_at', read_only=True)
    unread_count = serializers.SerializerMethodField()
    is_paygated = serializers.BooleanField(source='is_premium')
    
    class Meta:
        model = Thread
        fields = [
            'id', 'participants', 'is_paygated', 'price_stx', 'price_usdcx', 
            'last_message_at', 'unread_count', 'last_message', 'created_at'
        ]
    
    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return MessageSerializer(last_msg).data
        return None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request or not request.user:
            return 0
        return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
