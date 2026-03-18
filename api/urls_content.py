"""
URL routes for DAP credit, content generation, agent, and social agent proxy endpoints.
Mounted at /api/ in the project urls.py.
"""
from django.urls import path
from . import views_ops

urlpatterns = [
    # DAP Credit Service
    path('dap/status/',                              views_ops.dap_status,          name='dap_status'),
    path('dap/register/',                            views_ops.dap_register,        name='dap_register'),
    path('dap/balance/<str:address>/',               views_ops.dap_balance,         name='dap_balance'),
    path('dap/transactions/<str:address>/',          views_ops.dap_transactions,    name='dap_transactions'),
    path('dap/deduct/',                              views_ops.dap_deduct,          name='dap_deduct'),

    # Content Generation
    path('content/generate/',                        views_ops.content_generate,    name='content_generate'),
    path('content/status/',                          views_ops.content_status,      name='content_status'),
    path('content/latest/',                          views_ops.content_latest,      name='content_latest'),
    path('content/history/',                         views_ops.content_history,     name='content_history'),
    path('content/thumbnail/<str:date>/<str:format>/', views_ops.content_thumbnail, name='content_thumbnail'),

    # Long Elio Agent
    path('agent/wallet/',                            views_ops.agent_wallet,        name='agent_wallet'),
    path('agent/chat/',                              views_ops.agent_chat,          name='agent_chat'),

    # Social Agent
    path('agent/social/wallet/',                     views_ops.social_wallet,          name='social_wallet'),
    path('agent/social/status/',                     views_ops.social_status,          name='social_status'),
    path('agent/social/balance/',                    views_ops.social_balance,         name='social_balance'),
    path('agent/social/transactions/',               views_ops.social_transactions,    name='social_transactions'),

    # Admin Content Generation (direct trigger, no DAP credits)
    path('content/generate-admin/',                  views_ops.content_generate_admin,   name='content_generate_admin'),
    path('content/generate-stacks/',                 views_ops.content_generate_stacks,  name='content_generate_stacks'),

]
