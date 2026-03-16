"""
URL configuration for deorganized project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from api.views import health_check, serve_media
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API Routes
    path('api/', include('api.routers')),
    path('api/', include('merch.urls')),
    path('api/messages/', include('messaging.urls')),
    
    # DCPE Operations proxy endpoints
    path('ops/', include('api.urls_ops')),
    
    # JWT Authentication
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Health Check (Public)
    path('health/', health_check, name='health_check'),
    
    # Debug endpoint (remove in production later)
    path('api/debug/media/', lambda request: __import__('api.debug_views', fromlist=['debug_media_files']).debug_media_files(request)),
    
    # Custom media serving (bypasses WhiteNoise)
    re_path(r'^media/(?P<path>.*)$', serve_media, name='serve_media'),
]

# Serve static files in development only (production uses collectstatic)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

