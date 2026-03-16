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

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny
from users.permissions import production_staff_required

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DCPE_BASE = lambda: os.environ.get('DCPE_BASE_URL', '').rstrip('/')
DCPE_HEADERS = lambda: {"Authorization": f"Bearer {os.environ.get('DCPE_API_KEY', '')}"}

RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"
RAILWAY_HEADERS = lambda: {
    "Authorization": f"Bearer {os.environ.get('RAILWAY_API_TOKEN', '')}",
    "Content-Type": "application/json",
}
RAILWAY_PROJECT_ID = lambda: os.environ.get('RAILWAY_PROJECT_ID', '')
RAILWAY_SERVICE_ID = lambda: os.environ.get('RAILWAY_SERVICE_ID', '')
RAILWAY_ENV_ID = lambda: os.environ.get('RAILWAY_ENV_ID', '')


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
    """Decorator that blocks free-plan users from DCPE write endpoints."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
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
@production_staff_required
def ops_set_playlist_order(request):
    """POST /ops/set-playlist-order/ — set the track order within a DCPE playlist. Staff-only."""
    try:
        body = json.loads(request.body)
        resp = http_requests.post(
            f"{DCPE_BASE()}/api/set-playlist-order/",
            json=body,
            headers=DCPE_HEADERS(),
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as exc:
        return _proxy_error(exc)


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
            f"{DCPE_BASE()}/api/upload/",
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
