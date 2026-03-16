"""
URL routes for DCPE operations proxy endpoints.
Mounted at /ops/ in the project urls.py.
"""
from django.urls import path
from . import views_ops

app_name = 'ops'

urlpatterns = [
    # DCPE proxy endpoints (any authenticated user)
    path('health/', views_ops.ops_health, name='health'),
    path('status/', views_ops.ops_status, name='status'),
    path('playlists/', views_ops.ops_playlists, name='playlists'),
    path('set-playlist/', views_ops.ops_set_playlist, name='set_playlist'),
    path('advance/', views_ops.ops_advance, name='advance'),
    path('stream-start/', views_ops.ops_stream_start, name='stream_start'),
    path('stream-stop/', views_ops.ops_stream_stop, name='stream_stop'),

    # Railway GraphQL endpoints (admin only)
    path('set-mode/', views_ops.ops_set_mode, name='set_mode'),
    path('remove/', views_ops.ops_remove, name='remove'),

    # Content management (requires active subscription)
    path('create-folder/', views_ops.ops_create_folder, name='create_folder'),
    path('upload/', views_ops.ops_upload, name='upload'),
]
