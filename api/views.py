from django.http import JsonResponse, FileResponse, Http404
from django.conf import settings
from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
import os

from .models import Feedback
from .serializers import FeedbackSerializer

def health_check(request):
    """Public health check endpoint for monitoring."""
    return JsonResponse({'status': 'ok', 'message': 'Deorganized backend is running.'})


def serve_media(request, path):
    """
    Securely serve media files in production/staging environments.
    Bypasses WhiteNoise and provides a robust alternative to lambda-shorthand.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    
    if not os.path.exists(file_path):
        raise Http404("Media file not found")
    
    # We use FileResponse which is more efficient and handles context management
    return FileResponse(open(file_path, 'rb'), content_type=None)


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
