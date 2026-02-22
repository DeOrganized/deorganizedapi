from rest_framework import serializers
from .models import Feedback


class FeedbackSerializer(serializers.ModelSerializer):
    """Serializer for Feedback submissions"""
    
    class Meta:
        model = Feedback
        fields = ['id', 'category', 'message', 'user_identifier', 'created_at', 'resolved', 'admin_notes']
        read_only_fields = ['id', 'created_at']
    
    def create(self, validated_data):
        """Create and return a new Feedback instance"""
        return Feedback.objects.create(**validated_data)

