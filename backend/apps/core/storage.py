"""Object storage for videos, thumbnails and question images.

Production uses a private Cloudflare R2 bucket with presigned URLs, so file bytes never pass through Django.
When R2 is not configured (local dev, CI) `LocalSignedStorage` signs URLs to Django dev endpoints that
read/write MEDIA_ROOT, with the same expiry semantics.
"""

import re
import uuid
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.urls import reverse

KEY_RE = re.compile(r"^(videos|thumbnails|questions|photos)/[A-Za-z0-9/_\-.]{1,200}$")
ALLOWED_CONTENT_TYPES = {
    "videos": {"video/mp4"},
    "thumbnails": {"image/webp", "image/jpeg", "image/png"},
    "questions": {"image/webp", "image/jpeg", "image/png"},
    "photos": {"image/webp", "image/jpeg", "image/png"},
}
EXTENSIONS = {"video/mp4": "mp4", "image/webp": "webp", "image/jpeg": "jpg", "image/png": "png"}


class StorageError(ValueError):
    pass


def validate_key(key):
    if not key or not KEY_RE.match(key) or ".." in key:
        raise StorageError("Invalid storage key.")
    return key


def new_key(kind, content_type):
    if kind not in ALLOWED_CONTENT_TYPES:
        raise StorageError("Unknown upload kind.")
    if content_type not in ALLOWED_CONTENT_TYPES[kind]:
        raise StorageError(f"Content type {content_type!r} is not allowed for {kind}.")
    return f"{kind}/{uuid.uuid4().hex}.{EXTENSIONS[content_type]}"


class R2Storage:
    def __init__(self):
        import boto3
        from botocore.config import Config

        endpoint = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        cfg = Config(signature_version="s3v4", region_name="auto")
        self.bucket = settings.R2_BUCKET
        # Least privilege: the read key cannot write and the write key is only used for uploads.
        self.reader = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.R2_READ_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_READ_SECRET_ACCESS_KEY,
            config=cfg,
        )
        self.writer = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.R2_WRITE_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_WRITE_SECRET_ACCESS_KEY,
            config=cfg,
        )

    def upload_url(self, key, content_type, ttl):
        url = self.writer.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": validate_key(key), "ContentType": content_type},
            ExpiresIn=ttl,
        )
        return {"url": url, "method": "PUT", "headers": {"Content-Type": content_type}}

    def download_url(self, key, ttl):
        return self.reader.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": validate_key(key)}, ExpiresIn=ttl
        )

    def exists(self, key):
        try:
            self.reader.head_object(Bucket=self.bucket, Key=validate_key(key))
            return True
        except Exception:  # noqa: BLE001 - any failure means "not usable"
            return False


class LocalSignedStorage:
    SALT = "truescore.dev-storage"

    def root(self):
        return Path(settings.MEDIA_ROOT).resolve()

    def path_for(self, key):
        path = (self.root() / validate_key(key)).resolve()
        if self.root() not in path.parents:
            raise StorageError("Invalid storage key.")
        return path

    def sign(self, key, op, content_type=""):
        return signing.dumps({"k": key, "op": op, "ct": content_type}, salt=self.SALT, compress=True)

    def unsign(self, token, op, max_age):
        data = signing.loads(token, salt=self.SALT, max_age=max_age)
        if data.get("op") != op:
            raise signing.BadSignature("wrong operation")
        return data

    def upload_url(self, key, content_type, ttl):
        token = self.sign(validate_key(key), "put", content_type)
        url = reverse("dev-storage-upload", args=[token])
        return {"url": url, "method": "PUT", "headers": {"Content-Type": content_type}}

    def download_url(self, key, ttl):
        return reverse("dev-storage-download", args=[self.sign(validate_key(key), "get")])

    def exists(self, key):
        try:
            return self.path_for(key).is_file()
        except StorageError:
            return False


@lru_cache(maxsize=1)
def get_storage():
    if settings.R2_ACCOUNT_ID and settings.R2_BUCKET:
        return R2Storage()
    return LocalSignedStorage()
