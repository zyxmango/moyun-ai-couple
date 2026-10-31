"""Local/S3-compatible binary object storage.

Database columns keep a stable ``s3://bucket/key`` reference. API responses
resolve it to a short-lived signed URL, so buckets can remain private.
"""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path, PurePosixPath
from threading import Lock
from urllib.parse import urlparse

from ..config import settings


class ObjectStorage:
    def __init__(self) -> None:
        self._client = None
        self._public_client = None
        self._bucket_ready = False
        self._lock = Lock()

    @property
    def uses_s3(self) -> bool:
        return settings.STORAGE_BACKEND == "s3"

    def _new_client(self, endpoint_url: str | None):
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _s3(self):
        if self._client is None:
            if not settings.S3_ACCESS_KEY or not settings.S3_SECRET_KEY:
                raise RuntimeError("S3_ACCESS_KEY 和 S3_SECRET_KEY 尚未配置")
            self._client = self._new_client(settings.S3_ENDPOINT_URL)
        return self._client

    def _s3_public(self):
        if self._public_client is None:
            endpoint = settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL
            self._public_client = self._new_client(endpoint)
        return self._public_client

    def ensure_bucket(self) -> None:
        if not self.uses_s3 or self._bucket_ready:
            return
        with self._lock:
            if self._bucket_ready:
                return
            client = self._s3()
            try:
                client.head_bucket(Bucket=settings.S3_BUCKET)
            except Exception:
                create_args = {"Bucket": settings.S3_BUCKET}
                if settings.S3_REGION and settings.S3_REGION != "us-east-1":
                    create_args["CreateBucketConfiguration"] = {
                        "LocationConstraint": settings.S3_REGION,
                    }
                client.create_bucket(**create_args)
            self._bucket_ready = True

    @staticmethod
    def _safe_extension(filename: str | None, default: str = "bin") -> str:
        suffix = Path(filename or "").suffix.lower().lstrip(".")
        if suffix and suffix.isalnum() and len(suffix) <= 10:
            return suffix
        return default

    def put(
        self,
        category: str,
        content: bytes,
        original_filename: str | None = None,
        content_type: str | None = None,
    ) -> str:
        extension = self._safe_extension(original_filename)
        filename = f"{uuid.uuid4().hex}.{extension}"
        parts = PurePosixPath(category).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("非法的对象存储目录")
        safe_category = "/".join(parts)

        if not self.uses_s3:
            target_dir = settings.UPLOAD_DIR / safe_category
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / filename).write_bytes(content)
            return f"/uploads/{safe_category}/{filename}"

        self.ensure_bucket()
        key = f"{safe_category}/{filename}"
        detected_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self._s3().put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=content,
            ContentType=detected_type,
        )
        return f"s3://{settings.S3_BUCKET}/{key}"

    @staticmethod
    def _parse_s3_uri(value: str) -> tuple[str, str] | None:
        if not value or not value.startswith("s3://"):
            return None
        parsed = urlparse(value)
        key = parsed.path.lstrip("/")
        return (parsed.netloc, key) if parsed.netloc and key else None

    def url(self, value: str | None) -> str:
        if not value:
            return ""
        parsed = self._parse_s3_uri(value)
        if not parsed:
            return value
        bucket, key = parsed
        return self._s3_public().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=max(60, min(settings.S3_PRESIGN_TTL_SECONDS, 604800)),
        )

    def delete(self, value: str | None) -> None:
        if not value:
            return
        parsed = self._parse_s3_uri(value)
        if parsed:
            bucket, key = parsed
            self._s3().delete_object(Bucket=bucket, Key=key)
            return
        if value.startswith("/uploads/"):
            relative = value.removeprefix("/uploads/")
            target = (settings.UPLOAD_DIR / relative).resolve()
            upload_root = settings.UPLOAD_DIR.resolve()
            if target.is_relative_to(upload_root):
                target.unlink(missing_ok=True)


object_storage = ObjectStorage()
