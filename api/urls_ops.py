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
    path('set-playlist-order/', views_ops.ops_set_playlist_order, name='set_playlist_order'),
    path('advance/', views_ops.ops_advance, name='advance'),
    path('stream-start/', views_ops.ops_stream_start, name='stream_start'),
    path('stream-stop/', views_ops.ops_stream_stop, name='stream_stop'),

    # Railway GraphQL endpoints (admin only)
    path('set-mode/', views_ops.ops_set_mode, name='set_mode'),
    path('remove/', views_ops.ops_remove, name='remove'),

    # Content management (requires active subscription)
    path('create-folder/', views_ops.ops_create_folder, name='create_folder'),
    path('upload/', views_ops.ops_upload, name='upload'),

    # Creator Studio DCPE endpoints (authenticated creator + active subscription)
    path('dcpe/upload/',                       views_ops.dcpe_creator_upload,        name='dcpe_creator_upload'),
    path('dcpe/prep/',                         views_ops.dcpe_creator_prep,          name='dcpe_creator_prep'),
    path('dcpe/prep-status/<str:prep_id>/',    views_ops.dcpe_creator_prep_status,   name='dcpe_creator_prep_status'),
    path('dcpe/set-playlist/',                 views_ops.dcpe_creator_set_playlist,  name='dcpe_creator_set_playlist'),
    path('dcpe/stream-start/',                 views_ops.dcpe_creator_stream_start,  name='dcpe_creator_stream_start'),
    path('dcpe/stream-stop/',                  views_ops.dcpe_creator_stream_stop,   name='dcpe_creator_stream_stop'),
    path('dcpe/status/',                       views_ops.dcpe_creator_status,        name='dcpe_creator_status'),
]
