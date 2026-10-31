import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import settings
from app.services.object_storage import ObjectStorage


class LocalObjectStorageTest(unittest.TestCase):
    def test_local_put_resolve_and_delete(self):
        storage = ObjectStorage()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(settings, "STORAGE_BACKEND", "local"), patch.object(
            settings, "UPLOAD_DIR", Path(temp_dir)
        ):
            reference = storage.put(
                "couples/7/album",
                b"image-bytes",
                "holiday.JPG",
                "image/jpeg",
            )
            self.assertTrue(reference.startswith("/uploads/couples/7/album/"))
            self.assertEqual(storage.url(reference), reference)
            target = Path(temp_dir) / reference.removeprefix("/uploads/")
            self.assertEqual(target.read_bytes(), b"image-bytes")

            storage.delete(reference)
            self.assertFalse(target.exists())

    def test_invalid_extension_falls_back_to_bin(self):
        storage = ObjectStorage()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(settings, "STORAGE_BACKEND", "local"), patch.object(
            settings, "UPLOAD_DIR", Path(temp_dir)
        ):
            reference = storage.put("photos", b"x", "unsafe.$$$")
            self.assertTrue(reference.endswith(".bin"))

    def test_s3_keeps_stable_reference_and_returns_signed_url(self):
        class FakeS3:
            def __init__(self):
                self.created = False
                self.objects = []

            def head_bucket(self, **_kwargs):
                if not self.created:
                    raise RuntimeError("missing")

            def create_bucket(self, **_kwargs):
                self.created = True

            def put_object(self, **kwargs):
                self.objects.append(kwargs)

            def generate_presigned_url(self, _operation, Params, ExpiresIn):
                return f"https://objects.test/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"

        storage = ObjectStorage()
        fake = FakeS3()
        storage._client = fake
        storage._public_client = fake
        with patch.object(settings, "STORAGE_BACKEND", "s3"), patch.object(
            settings, "S3_BUCKET", "private"
        ), patch.object(settings, "S3_PRESIGN_TTL_SECONDS", 900):
            reference = storage.put("couples/7/chat", b"image", "photo.png", "image/png")
            self.assertTrue(reference.startswith("s3://private/couples/7/chat/"))
            self.assertEqual(fake.objects[0]["ContentType"], "image/png")
            self.assertIn("?ttl=900", storage.url(reference))


if __name__ == "__main__":
    unittest.main()
