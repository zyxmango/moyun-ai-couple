import unittest
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base, get_db
from app.main import app
import app.routers.chat as chat_router
from app.models import Couple, MemorySyncJob, User
from app.services.memory_jobs import enqueue_memory_sync
from app.services.rate_limit import enforce_rate_limit
from app.services.uploads import validate_image_bytes
from app.utils import create_access_token, hash_password


class SecurityHardeningTest(unittest.TestCase):
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
        self.original_chat_session_local = chat_router.SessionLocal
        chat_router.SessionLocal = self.sessions
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        chat_router.SessionLocal = self.original_chat_session_local
        self.client.close()
        self.engine.dispose()

    def test_production_defaults_fail_closed(self):
        settings = Settings()
        settings.APP_ENV = "production"
        settings.SECRET_KEY = "change-me"
        settings.ALLOW_LOCAL_VERIFICATION_CODE = True
        settings.CORS_ORIGINS = ["*"]
        settings.SMTP_EMAIL = ""
        settings.SMTP_AUTH_CODE = ""
        with self.assertRaises(RuntimeError):
            settings.validate_runtime()

    def test_image_content_signature_is_checked(self):
        validate_image_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 20, 1024)
        with self.assertRaises(HTTPException):
            validate_image_bytes(b"not really an image", 1024)

    def test_rate_limit_returns_429(self):
        key = uuid4().hex
        enforce_rate_limit("test", key, 1, 60)
        with self.assertRaises(HTTPException) as raised:
            enforce_rate_limit("test", key, 1, 60)
        self.assertEqual(raised.exception.status_code, 429)

    def test_dead_letter_job_requires_explicit_retry(self):
        with self.sessions() as db:
            db.add(MemorySyncJob(couple_id=999, status="dead_letter", attempts=8))
            db.commit()
            enqueue_memory_sync(db, 999)
            self.assertEqual(db.get(MemorySyncJob, 999).status, "dead_letter")
            enqueue_memory_sync(db, 999, revive_dead_letter=True)
            job = db.get(MemorySyncJob, 999)
            self.assertEqual(job.status, "pending")
            self.assertEqual(job.attempts, 0)

    def test_pairing_code_expires_and_websocket_authenticates_in_first_message(self):
        with self.sessions() as db:
            owner = User(email="owner@example.com", password_hash=hash_password("password123"))
            partner = User(email="partner@example.com", password_hash=hash_password("password123"))
            db.add_all([owner, partner])
            db.commit()
            db.refresh(owner)
            db.refresh(partner)
            owner_headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
            partner_headers = {"Authorization": f"Bearer {create_access_token(partner.id)}"}
            owner_id, partner_id = owner.id, partner.id

        generated = self.client.post("/api/auth/couple/generate", headers=owner_headers)
        self.assertEqual(generated.status_code, 200)
        self.assertTrue(generated.json()["expires_at"])
        bound = self.client.post(
            "/api/auth/couple/bind",
            json={"pairing_code": generated.json()["pairing_code"]},
            headers=partner_headers,
        )
        self.assertEqual(bound.status_code, 200)

        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"type": "auth", "token": create_access_token(owner_id)})
            self.assertEqual(websocket.receive_json()["type"], "auth_ok")
            self.assertEqual(websocket.receive_json()["type"], "unread_count")

        with self.sessions() as db:
            couple = db.query(Couple).filter(Couple.user1_id == owner_id).one()
            self.assertEqual(couple.user2_id, partner_id)


if __name__ == "__main__":
    unittest.main()
