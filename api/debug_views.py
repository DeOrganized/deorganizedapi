from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods
import os


@require_http_methods(["GET"])
def debug_media_files(request):
    """Debug endpoint to check media file system"""
    
    media_root = str(settings.MEDIA_ROOT)
    media_url = settings.MEDIA_URL
    
    # List all files in media directory
    def list_files(directory):
        files = []
        try:
            for root, dirs, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, directory)
                    files.append({
                        'filename': filename,
                        'path': filepath,
                        'relative_path': rel_path,
                        'url': f"{media_url}{rel_path.replace(os.sep, '/')}",
                        'size': os.path.getsize(filepath),
                        'exists': os.path.exists(filepath)
                    })
        except Exception as e:
            return {'error': str(e)}
        return files
    
    return JsonResponse({
        'media_root': media_root,
        'media_url': media_url,
        'media_root_exists': os.path.exists(media_root),
        'files': list_files(media_root),
        'total_files': len(list_files(media_root)) if isinstance(list_files(media_root), list) else 0
    })
