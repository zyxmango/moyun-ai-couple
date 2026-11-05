import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Couple, Photo, User
from app.utils import create_access_token, hash_password


class MediaUploadTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_patch = patch.object(settings, "STORAGE_BACKEND", "local")
        self.upload_patch = patch.object(settings, "UPLOAD_DIR", Path(self.temp_dir.name))
        self.storage_patch.start()
        self.upload_patch.start()
        self.client = TestClient(app)

        with self.sessions() as db:
            owner = User(
                email="media-owner@example.com",
                nickname="测试用户",
                password_hash=hash_password("password123"),
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)
            couple = Couple(pairing_code="MEDIA001", user1_id=owner.id, status="active")
            db.add(couple)
            db.commit()
            db.refresh(couple)
            owner.couple_id = couple.id
            db.commit()
            self.owner_id = owner.id
        self.headers = {"Authorization": f"Bearer {create_access_token(self.owner_id)}"}

    def tearDown(self):
        self.client.close()
        self.upload_patch.stop()
        self.storage_patch.stop()
        self.temp_dir.cleanup()
        app.dependency_overrides.clear()
        self.engine.dispose()

    @staticmethod
    def mp4_bytes():
        return b"\x00\x00\x00\x18ftypisom" + b"test-video-payload"

    def test_album_accepts_lists_and_deletes_video(self):
        uploaded = self.client.post(
            "/api/album",
            headers=self.headers,
            files={"file": ("memory.mp4", self.mp4_bytes(), "video/mp4")},
        )
        self.assertEqual(uploaded.status_code, 200)
        payload = uploaded.json()
        self.assertEqual(payload["media_type"], "video")

        listed = self.client.get("/api/album", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["media_type"], "video")
        self.assertEqual(listed.json()[0]["mime_type"], "video/mp4")
        self.assertEqual(listed.json()[0]["file_size"], len(self.mp4_bytes()))

        with self.sessions() as db:
            stored = db.get(Photo, payload["id"])
            path = Path(self.temp_dir.name) / stored.file_path.removeprefix("/uploads/")
            self.assertTrue(path.exists())

        deleted = self.client.delete(f"/api/album/{payload['id']}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(path.exists())

    def test_chat_video_is_persisted_and_history_resolves_url(self):
        uploaded = self.client.post(
            "/api/chat/upload",
            headers=self.headers,
            files={"file": ("chat.webm", b"\x1aE\xdf\xa3video", "video/webm")},
        )
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.json()["message"]["msg_type"], "video")

        history = self.client.get("/api/chat/history", headers=self.headers)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["msg_type"], "video")
        self.assertTrue(history.json()[0]["content"].startswith("/uploads/couples/"))


if __name__ == "__main__":
    unittest.main()
