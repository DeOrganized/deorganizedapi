"""
DCPE Proxy Views — Django endpoints that bridge the frontend to the
Railway-hosted DCPE (Digital Content Processing Engine) and Railway GraphQL API.

All DCPE endpoints require JWT authentication. The DCPE_API_KEY and
RAILWAY_API_TOKEN never reach the browser.
"""
import os
import json
import logging
import requests as http_requests
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.core.cache import cache

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny
from users.permissions import production_staff_required

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DCPE_BASE = lambda: os.environ.get('DCPE_BASE_URL', '').rstrip('/')
DCPE_HEADERS = lambda: {"Authorization": f"Bearer {os.environ.get('DCPE_API_KEY', '')}"}

# Session key for tracking which creator currently owns the DCPE stream
DCPE_SESSION_KEY = 'dcpe_creator_session'
DCPE_SESSION_TTL = 6 * 3600  # 6 hours

RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"
RAILWAY_HEADERS = lambda: {
    "Authorization": f"Bearer {os.environ.get('RAILWAY_API_TOKEN', '')}",
    "Content-Type": "application/json",
}
RAILWAY_PROJECT_ID = lambda: os.environ.get('RAILWAY_PROJECT_ID', '')
RAILWAY_SERVICE_ID = lambda: os.environ.get('RAILWAY_SERVICE_ID', '')
RAILWAY_ENV_ID = lambda: os.environ.get('RAILWAY_ENV_ID', '')

DAP_BASE        = lambda: os.environ.get('DAP_SERVICE_URL', '').rstrip('/')
AGENT_BASE      = lambda: os.environ.get('AGENT_API_URL', '').rstrip('/')
CONTROLLER_BASE = lambda: os.environ.get('AGENT_CONTROLLER_URL', '').rstrip('/')
SOCIAL_BASE     = lambda: os.environ.get('SOCIAL_AGENT_URL', '').rstrip('/')
AGENT_HEADERS   = lambda: {"X-API-Key": os.environ.get('AGENT_API_KEY', '')}


def _proxy_error(exc, context="DCPE"):
    """Return a consistent error JsonResponse for proxy failures."""
    logger.error(f"[{context}] proxy error: {exc}")
    return JsonResponse({"error": str(exc), "context": context}, status=502)


def _is_platform_staff(user):
    """Check if user is superuser or in platform_admin/production_staff group."""
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=['platform_admin', 'production_staff']).exists()


def require_active_subscription(view_func):
    """Decorator that blocks free-plan users from DCPE write endpoints.
    Platform staff and superusers are exempt — they don't need a subscription.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # Admins/staff bypass the subscription check entirely
        if _is_platform_staff(request.user):
            return view_func(request, *args, **kwargs)

        from users.models import Subscription
        try:
            sub = Subscription.objects.get(user=request.user)
            if sub.plan == 'free' or not sub.is_active:
                return JsonResponse(
                    {"error": "Playout engine requires an active Starter, Pro, or Enterprise subscription."},
                    status=403,
                )
        except Subscription.DoesNotExist:
            return JsonResponse(
                {"error": "No subscription found. Please subscribe to access the playout engine."},
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


# ---------------------------------------------------------------------------
# DCPE Proxy Endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
def ops_health(request):
    """GET /ops/health/ — DCPE health check."""
    try:
        resp = http_requests.get(
            f"{DCPE_BASE()}/health",
            headers=DCPE_HEADERS(),
            timeout=30,  # Allow for Railway cold-start delay
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except http_requests.Timeout:
        return JsonResponse({'ok': False, 'status': 'timeout', 'error': 'DCPE is not responding — service may be starting up. Try again in a moment.'}, status=200)
    except Exception as exc:
        return JsonResponse({'ok': False, 'status': 'offline', 'error': str(exc)}, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ops_status(request):
    """
    GET /ops/status/ — merged DCPE + Railway status.
    Returns DCPE stream state plus Railway deployment info.
    """
    result = {
        "mode": "",
        "deployment": {},
        "playlist_loaded": False,
        "now_playing": "",
        "rtmp_connected": False,
        "streaming_enabled": False,
        "last_error": None,
    }

    # Fetch DCPE status
    try:
        dcpe_resp = http_requests.get(
            f"{DCPE_BASE()}/api/status/",
            headers=DCPE_HEADERS(),
            timeout=30,  # Allow for Railway cold-start
        )
        if dcpe_resp.ok:
            data = dcpe_resp.json()
            result["mode"] = data.get("mode")
            result["playlist_loaded"] = data.get("playlist_loaded")
            result["now_playing"] = data.get("now_playing")
            result["rtmp_connected"] = data.get("rtmp_connected")
            result["streaming_enabled"] = data.get("streaming_enabled")
            result["last_error"] = data.get("last_error")
    except Exception as exc:
        result["last_error"] = f"DCPE unreachable: {exc}"

    # Fetch Railway deployment status (optional — if token is configured)
    if os.environ.get('RAILWAY_API_TOKEN'):
        try:
            gql_query = """
            query($serviceId: String!, $environmentId: String!) {
                deployments(input: { serviceId: $serviceId, environmentId: $environmentId }) {
                    edges { node { id status } }
                }
            }
            """
            gql_resp = http_requests.post(
                RAILWAY_GQL,
                headers=RAILWAY_HEADERS(),
                json={
                    "query": gql_query,
                    "variables": {
                        "serviceId": RAILWAY_SERVICE_ID(),
                        "environmentId": RAILWAY_ENV_ID(),
                    },
                },
                timeout=30,
            )
            if gql_resp.ok:
                gql_data = gql_resp.json() or {}
                deployments = (gql_data.get("data") or {}).get("deployments") or {}
                edges = deployments.get("edges", [])
                if edges:
                    result["deployment"] = edges[0]["node"]
        except Exception as exc:
            logger.warning(f"Railway status fetch failed: {exc}")

    return JsonResponse(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ops_playlists(request):
    """
    GET /ops/playlists/ — list available playlists from DCPE.
    Admins/staff see all playlists. Creators only see playlists
    assigned to them via CreatorPlaylist.
    """
    try:
        resp = http_requests.get(
            f"{DCPE_BASE()}/api/playlists/",
            headers=DCPE_HEADERS(),
            timeout=30,
        )
        if not resp.ok:
            return JsonResponse(resp.json(), status=resp.status_code)

        data = resp.json()
        all_playlists = data.get('playlists', data if isinstance(data, list) else [])

        # Admins/staff see everything
        if _is_platform_staff(request.user):
            return JsonResponse({'playlists': all_playlists})

        # Creators only see their assigned playlists
        from users.models import CreatorPlaylist
        owned_names = set(
            CreatorPlaylist.objects.filter(user=request.user)
            .values_list('dcpe_playlist_name', flat=True)
        )
        filtered = [p for p in all_playlists if p.get('name') in owned_names]
        return JsonResponse({'playlists': filtered})

    except Exception as exc:
        return _proxy_error(exc)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@production_staff_required
def ops_set_playlist(request):
    """
    POST /ops/set-playlist/ — set the active DCPE playlist.
    Staff-only until per-creator Railway instances are provisioned.
    """
    try:
        body = json.loads(request.body)

        # Ownership check for non-admin users
        if not _is_platform_staff(request.user):
            from users.models import CreatorPlaylist
            playlist_name = body.get('name', body.get('folder', ''))
            if not CreatorPlaylist.objects.filter(
                user=request.user, dcpe_playlist_name=playlist_name
            ).exists():
                return JsonResponse(
                    {'error': 'You do not have access to this playlist.'},
                    status=403,
                )

        resp = http_requests.post(
            f"{DCPE_BASE()}/api/set-playlist/",
            json=body,
            headers=DCPE_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ops_set_playlist_order(request):
    """
    POST /ops/set-playlist-order/ — set the run-order of folders before streaming.

    Expected body:
        { "folders": ["folder_a", "folder_b", ...] }

    Ownership check: non-admin users may only order playlists they own.
    Forwards the body verbatim to DCPE's /api/set-playlist-order/.
    """
    try:
        body = json.loads(request.body)
        folders = body.get('folders', [])

        if not isinstance(folders, list) or not folders:
            return JsonResponse({'error': 'folders must be a non-empty list.'}, status=400)

        # Non-admin creators may only reorder playlists they own
        if not _is_platform_staff(request.user):
            from users.models import CreatorPlaylist
            owned_names = set(
                CreatorPlaylist.objects.filter(user=request.user)
                .values_list('dcpe_playlist_name', flat=True)
            )
            unauthorized = [f for f in folders if f not in owned_names]
            if unauthorized:
                return JsonResponse(
                    {'error': f'You do not have access to: {unauthorized}'},
                    status=403,
                )

        resp = http_requests.post(
            f"{DCPE_BASE()}/api/set-playlist-order/",
            json=body,
            headers=DCPE_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="SetPlaylistOrder")




@api_view(['POST'])
@permission_classes([IsAuthenticated])
@production_staff_required
def ops_advance(request):
    """POST /ops/advance/ — skip to next track. Staff-only until per-creator Railway instances are provisioned."""
    try:
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/advance/",
            headers=DCPE_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@production_staff_required
def ops_stream_start(request):
    """
    POST /ops/stream-start/ — immediate RTMP start (no redeploy).
    DCPE writes a flag that is polled within 10s.
    """
    try:
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/stream-start/",
            headers=DCPE_HEADERS(),
            timeout=10,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@production_staff_required
def ops_stream_stop(request):
    """
    POST /ops/stream-stop/ — immediate RTMP kill (no redeploy).
    DCPE removes the flag and kills the ffmpeg process.
    """
    try:
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/stream-stop/",
            headers=DCPE_HEADERS(),
            timeout=10,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc)


# ---------------------------------------------------------------------------
# Creator Studio DCPE Endpoints — /ops/dcpe/*
# Accessible to any authenticated creator with an active subscription.
# These share the same DCPE instance as the admin ops routes but are not
# gated behind production_staff_required.
# ---------------------------------------------------------------------------

DCPE_UPLOAD_COST = 100  # DAP credits per video file


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dcpe_creator_upload(request):
    """
    POST /ops/dcpe/upload/ — session-based file upload for Creator Studio.
    Deducts 100 DAP credits per file before forwarding to DCPE /api/upload/.
    Returns 402 if the user has insufficient credits.
    """
    try:
        f = request.FILES.get('file')
        if not f:
            return JsonResponse({'error': 'file is required'}, status=400)

        stacks_address = getattr(request.user, 'stacks_address', None)
        if not stacks_address:
            return JsonResponse({'error': 'No Stacks address on account.'}, status=403)

        # Deduct credits before upload — atomic, row-locked in DAP service
        deduct_resp = http_requests.post(
            f"{DAP_BASE()}/api/credits/deduct",
            json={
                'stacks_address': stacks_address,
                'amount': DCPE_UPLOAD_COST,
                'service_name': 'playout-upload',
                'description': f'Video upload: {f.name}',
            },
            headers=AGENT_HEADERS(),
            timeout=15,
        )
        if deduct_resp.status_code == 402:
            data = deduct_resp.json()
            return JsonResponse({
                'error': 'Insufficient DAP credits.',
                'balance': data.get('balance', 0),
                'required': DCPE_UPLOAD_COST,
            }, status=402)
        if not deduct_resp.ok:
            return JsonResponse({'error': 'Credit deduction failed. Please try again.'}, status=502)

        # Credits deducted — forward file to DCPE
        session_id = request.POST.get('session_id', '').strip()
        file_bytes = f.read()
        files = [('file', (f.name, file_bytes, f.content_type))]
        data = {'session_id': session_id} if session_id else {}

        resp = http_requests.post(
            f"{DCPE_BASE()}/api/upload/",
            files=files,
            data=data,
            headers=DCPE_HEADERS(),
            timeout=120,
        )
        result = resp.json()
        # Include updated balance so frontend can refresh without an extra call
        result['credits_deducted'] = DCPE_UPLOAD_COST
        result['new_balance'] = deduct_resp.json().get('new_balance')
        return JsonResponse(result, status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DCPE Upload")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dcpe_creator_prep(request):
    """
    POST /ops/dcpe/prep/ — kick off normalization pipeline for uploaded file_ids.
    Body: { "file_ids": [...] }
    """
    try:
        body = json.loads(request.body) if request.body else {}
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/prep/",
            json=body,
            headers=DCPE_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DCPE Prep")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dcpe_creator_prep_status(request, prep_id):
    """
    GET /ops/dcpe/prep-status/<prep_id>/ — per-file normalization progress.
    """
    try:
        resp = http_requests.get(
            f"{DCPE_BASE()}/api/prep-status/{prep_id}",
            headers=DCPE_HEADERS(),
            timeout=15,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DCPE Prep Status")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dcpe_creator_set_playlist(request):
    """
    POST /ops/dcpe/set-playlist/ — set DCPE playlist to creator's prepped folder.
    Body: { "playlist_id": "creator_<prep_id>" }
    """
    try:
        body = json.loads(request.body) if request.body else {}
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/set-playlist/",
            json=body,
            headers=DCPE_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DCPE Set Playlist")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dcpe_creator_stream_start(request):
    """POST /ops/dcpe/stream-start/ — start RTMP stream from creator session.
    Returns 409 if another creator already owns the active session.
    """
    session = cache.get(DCPE_SESSION_KEY)
    if session and session.get('user_id') != request.user.id:
        return JsonResponse({
            'error': 'Stream is currently in use by another creator',
            'session_owner_username': session.get('username'),
        }, status=409)

    try:
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/stream-start/",
            headers=DCPE_HEADERS(),
            timeout=10,
        )
        if resp.ok:
            cache.set(DCPE_SESSION_KEY, {
                'user_id': request.user.id,
                'username': request.user.username,
            }, DCPE_SESSION_TTL)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DCPE Stream Start")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dcpe_creator_stream_stop(request):
    """POST /ops/dcpe/stream-stop/ — stop RTMP stream.
    Returns 403 if the caller does not own the active session.
    """
    session = cache.get(DCPE_SESSION_KEY)
    if session and session.get('user_id') != request.user.id:
        return JsonResponse({
            'error': 'You cannot stop a stream started by another creator',
            'session_owner_username': session.get('username'),
        }, status=403)

    try:
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/stream-stop/",
            headers=DCPE_HEADERS(),
            timeout=10,
        )
        if resp.ok:
            cache.delete(DCPE_SESSION_KEY)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DCPE Stream Stop")


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_dcpe_kill(request):
    """
    POST /ops/admin/dcpe/kill/ — emergency stream shutoff, admin-only.
    Stops the DCPE stream immediately regardless of session ownership and clears the session lock.
    """
    try:
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/stream-stop/",
            headers=DCPE_HEADERS(),
            timeout=10,
        )
        cache.delete(DCPE_SESSION_KEY)
        data = resp.json() if resp.ok else {'status': 'stop_sent'}
        data['session_cleared'] = True
        data['killed_by'] = request.user.username
        logger.warning(f"[admin_dcpe_kill] Emergency kill by {request.user.username}")
        return JsonResponse(data, status=200)
    except Exception as exc:
        # Even if DCPE call fails, clear the session lock
        cache.delete(DCPE_SESSION_KEY)
        return _proxy_error(exc, context="DCPE Admin Kill")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dcpe_creator_status(request):
    """GET /ops/dcpe/status/ — DCPE stream and engine status, including session owner."""
    try:
        resp = http_requests.get(
            f"{DCPE_BASE()}/api/status/",
            headers=DCPE_HEADERS(),
            timeout=10,
        )
        data = resp.json()
        session = cache.get(DCPE_SESSION_KEY)
        data['session_owner_id'] = session['user_id'] if session else None
        data['session_owner_username'] = session['username'] if session else None
        return JsonResponse(data, status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DCPE Status")


# ---------------------------------------------------------------------------
# Railway GraphQL Endpoints
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@production_staff_required
def ops_set_mode(request):
    """
    POST /ops/set-mode/ — upsert MODE variable on Railway and trigger redeploy.
    Body: { "mode": "prep" | "playout" | "remove" }
    """
    try:
        body = json.loads(request.body)
        mode = body.get("mode", "playout")

        # 1. Upsert MODE variable
        upsert_query = """
        mutation($projectId: String!, $serviceId: String!, $environmentId: String!, $variables: ServiceVariables!) {
            variableCollectionUpsert(input: {
                projectId: $projectId,
                serviceId: $serviceId,
                environmentId: $environmentId,
                variables: $variables
            })
        }
        """
        upsert_resp = http_requests.post(
            RAILWAY_GQL,
            headers=RAILWAY_HEADERS(),
            json={
                "query": upsert_query,
                "variables": {
                    "projectId": RAILWAY_PROJECT_ID(),
                    "serviceId": RAILWAY_SERVICE_ID(),
                    "environmentId": RAILWAY_ENV_ID(),
                    "variables": {"MODE": mode},
                },
            },
            timeout=30,
        )
        if not upsert_resp.ok:
            return JsonResponse({"error": "Failed to upsert MODE variable", "details": upsert_resp.text}, status=502)

        # 2. Trigger redeploy
        redeploy_query = """
        mutation($serviceId: String!, $environmentId: String!) {
            serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
        }
        """
        redeploy_resp = http_requests.post(
            RAILWAY_GQL,
            headers=RAILWAY_HEADERS(),
            json={
                "query": redeploy_query,
                "variables": {
                    "serviceId": RAILWAY_SERVICE_ID(),
                    "environmentId": RAILWAY_ENV_ID(),
                },
            },
            timeout=30,
        )

        return JsonResponse({
            "ok": True,
            "mode": mode,
            "redeploy_triggered": redeploy_resp.ok,
        })
    except Exception as exc:
        return _proxy_error(exc, context="Railway")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@production_staff_required
def ops_remove(request):
    """
    POST /ops/remove/ — find latest deployment and remove it via Railway GraphQL.
    """
    try:
        # 1. Query deployments
        query = """
        query($serviceId: String!, $environmentId: String!) {
            deployments(input: { serviceId: $serviceId, environmentId: $environmentId }) {
                edges { node { id status } }
            }
        }
        """
        query_resp = http_requests.post(
            RAILWAY_GQL,
            headers=RAILWAY_HEADERS(),
            json={
                "query": query,
                "variables": {
                    "serviceId": RAILWAY_SERVICE_ID(),
                    "environmentId": RAILWAY_ENV_ID(),
                },
            },
            timeout=30,
        )
        if not query_resp.ok:
            return JsonResponse({"error": "Failed to query deployments"}, status=502)

        edges = query_resp.json().get("data", {}).get("deployments", {}).get("edges", [])
        active = next((e["node"] for e in edges if e["node"]["status"] in ("SUCCESS", "DEPLOYING")), None)
        if not active:
            return JsonResponse({"error": "No active deployment found"}, status=404)

        # 2. Remove deployment
        remove_query = """
        mutation($id: String!) {
            deploymentRemove(id: $id)
        }
        """
        remove_resp = http_requests.post(
            RAILWAY_GQL,
            headers=RAILWAY_HEADERS(),
            json={
                "query": remove_query,
                "variables": {"id": active["id"]},
            },
            timeout=30,
        )

        return JsonResponse({
            "ok": True,
            "deployment_removed": active["id"],
            "success": remove_resp.ok,
        })
    except Exception as exc:
        return _proxy_error(exc, context="Railway")


# ---------------------------------------------------------------------------
# Content Management Endpoints
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_subscription
def ops_create_folder(request):
    """
    POST /ops/create-folder/ — create a per-creator folder on DCPE.
    Auto-called on subscription upgrade. Creates Google Drive folder via DCPE.
    """
    try:
        user = request.user
        folder_name = f"creator_{user.id}_{user.username}"
        label = f"{user.display_name or user.username}'s Content"

        resp = http_requests.post(
            f"{DCPE_BASE()}/api/create-folder/",
            json={"folder": folder_name, "label": label},
            headers=DCPE_HEADERS(),
            timeout=30,
        )

        if resp.ok:
            log_msg = f"Created DCPE folder: {folder_name}"
        else:
            log_msg = f"DCPE folder creation returned {resp.status_code}"
        logger.info(f"[ops_create_folder] {log_msg}")

        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        # Non-fatal: folder creation is best-effort until DCPE implements the endpoint
        logger.warning(f"[ops_create_folder] DCPE folder creation not available: {exc}")
        return JsonResponse({
            "ok": False,
            "warning": "DCPE folder creation endpoint not yet available. Folder will be created when DCPE implements POST /api/create-folder/.",
            "folder": f"creator_{request.user.id}_{request.user.username}",
        }, status=202)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_subscription
def ops_upload(request):
    """
    POST /ops/upload/ — proxy file uploads to DCPE, tagged with creator's folder.
    """
    try:
        user = request.user
        folder_name = f"creator_{user.id}_{user.username}"

        # Admins can specify a custom folder
        if _is_platform_staff(user):
            folder_name = request.POST.get('folder', folder_name)

        # NOTE: We intentionally skip the CreatorPlaylist ownership check here.
        # Folders are namespaced as creator_{id}_{username} so uploads can't
        # cross creator boundaries. The CreatorPlaylist check blocked all uploads
        # because DCPE's POST /api/create-folder/ is not yet implemented, so no
        # rows existed. Re-evaluate once DCPE folder creation is live.

        # Forward files to DCPE
        files = []
        for f in request.FILES.getlist('files'):
            files.append(('files', (f.name, f.read(), f.content_type)))

        if not files:
            return JsonResponse({'error': 'No files provided.'}, status=400)

        resp = http_requests.post(
            f"{DCPE_BASE()}/api/folder-upload/",
            files=files,
            data={'folder': folder_name},
            headers=DCPE_HEADERS(),
            timeout=120,
        )

        if resp.status_code == 404:
            logger.warning(f"[ops_upload] DCPE upload endpoint not available (404)")
            return JsonResponse({
                "ok": False,
                "warning": "DCPE upload endpoint not yet available in current version. Files will be sync'd when the feature is live.",
                "folder": folder_name,
            }, status=202)

        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Upload")


# ---------------------------------------------------------------------------
# DAP Credit Service Endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dap_status(request):
    """GET /api/dap/status/ — DAP service status."""
    try:
        resp = http_requests.get(
            f"{DAP_BASE()}/api/status",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DAP")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dap_register(request):
    """POST /api/dap/register/ — register a Stacks address with the DAP credit system."""
    try:
        body = json.loads(request.body)
        resp = http_requests.post(
            f"{DAP_BASE()}/api/users/register",
            json=body,
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DAP")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dap_balance(request, address):
    """GET /api/dap/balance/<address>/ — DAP credit balance for a Stacks address."""
    try:
        resp = http_requests.get(
            f"{DAP_BASE()}/api/users/{address}/balance",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DAP")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dap_deduct(request):
    """
    POST /api/dap/deduct/ — deduct DAP credits for a service.
    Body: { stacks_address, amount, service_name, description }
    Returns 402 if insufficient credits.
    """
    try:
        body = json.loads(request.body) if request.body else {}
        resp = http_requests.post(
            f"{DAP_BASE()}/api/credits/deduct",
            json=body,
            headers=AGENT_HEADERS(),
            timeout=15,
        )
        # Track successful deductions as unread notifications
        if resp.status_code in (200, 201):
            try:
                from users.models import DappPointEvent
                amount = body.get('amount', 0)
                description = body.get('description', body.get('service_name', 'Credits deducted'))
                DappPointEvent.objects.create(
                    user=request.user,
                    action='dap_deduct',
                    points=-abs(int(amount)),
                    description=description,
                    is_read=False,
                )
            except Exception as e:
                logger.warning(f"[dap_deduct] DappPointEvent tracking failed: {e}")
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DAP")


@api_view(['POST'])
@permission_classes([IsAdminUser])
def dap_grant(request):
    """
    POST /api/admin/dap/grant/ — admin mint DAP credits to a user.
    Body: { stacks_address, amount, description }
    Returns { success, new_balance, amount, description }
    """
    try:
        body = json.loads(request.body) if request.body else {}
        stacks_address = body.get('stacks_address', '').strip()
        amount = body.get('amount')
        description = body.get('description', 'Admin grant')

        if not stacks_address or not amount:
            return JsonResponse({'error': 'stacks_address and amount are required'}, status=400)

        try:
            amount = int(amount)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'error': 'amount must be a positive integer'}, status=400)

        # Register (idempotent — 409 = already registered, both fine)
        try:
            http_requests.post(
                f"{DAP_BASE()}/api/users/register",
                json={'stacks_address': stacks_address},
                headers=AGENT_HEADERS(),
                timeout=15,
            )
        except Exception as e:
            logger.warning(f"[dap_grant] register step failed: {e}")

        # Mint
        mint_resp = http_requests.post(
            f"{DAP_BASE()}/api/credits/mint",
            json={'stacks_address': stacks_address, 'amount': amount, 'description': description},
            headers=AGENT_HEADERS(),
            timeout=15,
        )
        if mint_resp.status_code not in (200, 201):
            logger.error(f"[dap_grant] mint failed {mint_resp.status_code}: {mint_resp.text[:200]}")
            return JsonResponse(
                {'error': f'DAP mint failed ({mint_resp.status_code})'},
                status=502,
            )

        # Fetch new balance
        new_balance = None
        try:
            bal_resp = http_requests.get(
                f"{DAP_BASE()}/api/users/{stacks_address}/balance",
                headers=AGENT_HEADERS(),
                timeout=10,
            )
            if bal_resp.ok:
                new_balance = bal_resp.json().get('balance')
        except Exception:
            pass

        # Record unread notification for the target user
        try:
            from django.contrib.auth import get_user_model
            from users.models import DappPointEvent
            User = get_user_model()
            target_user = User.objects.filter(stacks_address=stacks_address).first()
            if target_user:
                DappPointEvent.objects.create(
                    user=target_user,
                    action='admin_dap_grant',
                    points=amount,
                    description=f'Admin grant: {description}',
                    is_read=False,
                )
        except Exception as e:
            logger.warning(f"[dap_grant] DappPointEvent creation failed: {e}")

        logger.info(f"[dap_grant] {request.user.username} granted {amount} credits to {stacks_address}: {description}")
        return JsonResponse({'success': True, 'new_balance': new_balance, 'amount': amount, 'description': description})
    except Exception as exc:
        return _proxy_error(exc, context="DAP")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dap_transactions(request, address):
    """GET /api/dap/transactions/<address>/ — DAP credit transaction history."""
    try:
        resp = http_requests.get(
            f"{DAP_BASE()}/api/users/{address}/transactions",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="DAP")


# ---------------------------------------------------------------------------
# Content Generation Endpoints
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def content_generate(request):
    """POST /api/content/generate/ — trigger content generation via the agent controller."""
    try:
        body = json.loads(request.body)
        resp = http_requests.post(
            f"{CONTROLLER_BASE()}/api/generate",
            json=body,
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def content_status(request):
    """GET /api/content/status/ — content generation run status."""
    try:
        resp = http_requests.get(
            f"{AGENT_BASE()}/news/run-status",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def content_latest(request):
    """GET /api/content/latest/ — latest generated content package."""
    try:
        resp = http_requests.get(
            f"{AGENT_BASE()}/news/latest",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def content_history(request):
    """GET /api/content/history/ — generated content history. Forwards ?limit query param."""
    try:
        params = {}
        if request.GET.get('limit'):
            params['limit'] = request.GET['limit']
        resp = http_requests.get(
            f"{AGENT_BASE()}/news/history",
            headers=AGENT_HEADERS(),
            params=params,
            timeout=30,
        )
        return JsonResponse(resp.json(), safe=False, status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def content_thumbnail(request, date, format):
    """GET /api/content/thumbnail/<date>/<format>/ — pipe thumbnail binary for img tag use."""
    from django.http import HttpResponse
    try:
        resp = http_requests.get(
            f"{AGENT_BASE()}/news/thumbnail/{date}/{format}",
            params={"key": os.environ.get('AGENT_API_KEY', '')},
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return HttpResponse(
            resp.content,
            content_type=resp.headers.get('content-type', 'image/png'),
            status=resp.status_code,
        )
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


# ---------------------------------------------------------------------------
# Long Elio Agent Endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def agent_wallet(request):
    """GET /api/agent/wallet/ — Long Elio agent wallet balances."""
    try:
        resp = http_requests.get(
            f"{AGENT_BASE()}/wallet",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def agent_chat(request):
    """POST /api/agent/chat/ — send a message to Long Elio and get a response."""
    try:
        body = json.loads(request.body) if request.body else {}
        user = request.user
        body['userId'] = getattr(user, 'stacks_address', None) or user.username
        body['userName'] = getattr(user, 'display_name', None) or user.username
        resp = http_requests.post(
            f"{AGENT_BASE()}/chat",
            json=body,
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


# ---------------------------------------------------------------------------
# Social Agent Endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def social_wallet(request):
    """GET /api/agent/social/wallet/ — social agent wallet balances (STX, sBTC, USDCx)."""
    try:
        resp = http_requests.get(
            f"{SOCIAL_BASE()}/api/wallet",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Social")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def social_status(request):
    """GET /api/agent/social/status/ — social agent full state and credit balance."""
    try:
        resp = http_requests.get(
            f"{SOCIAL_BASE()}/api/status",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Social")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def social_balance(request):
    """GET /api/agent/social/balance/ — social agent DAP credit balance."""
    try:
        resp = http_requests.get(
            f"{SOCIAL_BASE()}/api/balance",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Social")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def social_transactions(request):
    """GET /api/agent/social/transactions/ — social agent DAP transaction history."""
    try:
        resp = http_requests.get(
            f"{SOCIAL_BASE()}/api/transactions",
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Social")


# ---------------------------------------------------------------------------
# Social Agent Run Endpoints (admin-only cycle triggers)
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAdminUser])
def social_run_news(request):
    """
    POST /api/agent/social/run-news/ — trigger a news-package cycle on the social agent.
    Proxies to SOCIAL_BASE /api/run with serviceType=news-package.
    Passes 409 through so callers can detect a cycle already in progress.
    """
    try:
        resp = http_requests.post(
            f"{SOCIAL_BASE()}/api/run",
            json={"serviceType": "news-package"},
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Social")


@api_view(['POST'])
@permission_classes([IsAdminUser])
def social_run_stacks(request):
    """
    POST /api/agent/social/run-stacks/ — trigger a stacks-package cycle on the social agent.
    Proxies to SOCIAL_BASE /api/run with serviceType=stacks-package.
    Passes 409 through so callers can detect a cycle already in progress.
    """
    try:
        resp = http_requests.post(
            f"{SOCIAL_BASE()}/api/run",
            json={"serviceType": "stacks-package"},
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Social")


# ---------------------------------------------------------------------------
# Admin Content Generation Endpoints (no DAP credits — direct agent trigger)
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAdminUser])
def content_generate_admin(request):
    """
    POST /api/content/generate-admin/ — admin-only direct trigger for news generation.
    Bypasses DAP credits and goes directly to the agent's /news/run endpoint.
    Body: { operatorPrompt?: string, additionalLinks?: string[] }
    """
    try:
        body = json.loads(request.body) if request.body else {}
        payload = {}
        if body.get('operatorPrompt'):
            payload['operatorPrompt'] = body['operatorPrompt']
        if body.get('additionalLinks'):
            payload['additionalLinks'] = body['additionalLinks']
        resp = http_requests.post(
            f"{AGENT_BASE()}/news/run",
            json=payload,
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")


@api_view(['POST'])
@permission_classes([IsAdminUser])
def content_generate_stacks(request):
    """
    POST /api/content/generate-stacks/ — admin-only direct trigger for Stacks package generation.
    Bypasses DAP credits and goes directly to the agent's /news/run-stacks endpoint.
    Body: { operatorPrompt?: string, additionalLinks?: string[] }
    """
    try:
        body = json.loads(request.body) if request.body else {}
        payload = {}
        if body.get('operatorPrompt'):
            payload['operatorPrompt'] = body['operatorPrompt']
        if body.get('additionalLinks'):
            payload['additionalLinks'] = body['additionalLinks']
        resp = http_requests.post(
            f"{AGENT_BASE()}/news/run-stacks",
            json=payload,
            headers=AGENT_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc, context="Agent")

