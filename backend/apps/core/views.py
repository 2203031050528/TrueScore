"""Dev-only storage endpoints backing LocalSignedStorage. Disabled whenever R2 is configured."""

import mimetypes
import re

from django.conf import settings
from django.core import signing
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .storage import LocalSignedStorage, StorageError, get_storage

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 64 * 1024


def _local_storage():
    storage = get_storage()
    if not isinstance(storage, LocalSignedStorage):
        raise Http404
    return storage


@csrf_exempt  # authorised by the signed, expiring token in the URL, like an R2 presigned URL
@require_http_methods(["PUT"])
def dev_upload(request, token):
    storage = _local_storage()
    try:
        data = storage.unsign(token, "put", settings.VIDEO_UPLOAD_URL_TTL)
        path = storage.path_for(data["k"])
    except (signing.BadSignature, StorageError):
        return HttpResponse(status=403)
    if data["ct"] and request.content_type != data["ct"]:
        return HttpResponseBadRequest("Content-Type does not match the signed upload.")
    limit = settings.VIDEO_MAX_UPLOAD_BYTES if data["k"].startswith("videos/") else settings.IMAGE_MAX_UPLOAD_BYTES
    if int(request.META.get("CONTENT_LENGTH") or 0) > limit:
        return HttpResponse(status=413)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        while chunk := request.read(CHUNK):
            fh.write(chunk)
    return HttpResponse(status=200)


def _iter_range(path, start, length):
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            chunk = fh.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@require_http_methods(["GET", "HEAD"])
def dev_download(request, token):
    storage = _local_storage()
    try:
        data = storage.unsign(token, "get", settings.VIDEO_URL_TTL)
        path = storage.path_for(data["k"])
    except (signing.BadSignature, StorageError):
        return HttpResponse(status=403)
    if not path.is_file():
        raise Http404
    size = path.stat().st_size
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    match = RANGE_RE.match(request.headers.get("Range", ""))
    if match and (match.group(1) or match.group(2)):
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1
        else:  # suffix range: last N bytes
            start = max(size - int(match.group(2)), 0)
            end = size - 1
        end = min(end, size - 1)
        if start > end:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        response = StreamingHttpResponse(_iter_range(path, start, end - start + 1), status=206, content_type=content_type)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(end - start + 1)
    else:
        response = FileResponse(open(path, "rb"), content_type=content_type)
    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = "inline"
    return response
