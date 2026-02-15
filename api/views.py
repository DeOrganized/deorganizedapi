from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import Feedback
from .serializers import FeedbackSerializer

# Create your views here.

class FeedbackViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Feedback submissions - allows anyone to submit feedback.
    
    Create: POST /api/feedback/
    List: GET /api/feedback/ (staff only)
    """
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [AllowAny]  # Anyone can submit feedback
    http_method_names = ['post', 'get', 'patch']  # Only allow POST for creation, GET for admin, PATCH for admin notes
    
    def create(self, request, *args, **kwargs):
        """Handle feedback submission"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return Response({
            'success': True,
            'message': 'Feedback received successfully. Thank you for helping us improve!'
        }, status=status.HTTP_201_CREATED)
    
    def get_queryset(self):
        """Only staff can view all feedback"""
        if self.request.user.is_staff:
            return Feedback.objects.all()
        return Feedback.objects.none()
