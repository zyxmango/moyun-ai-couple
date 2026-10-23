"""AI 共同记忆端到端 API 测试（不调用外部模型）。"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Couple, Diary, Message, User
from app.services.ai_service import ai_service
from app.utils import create_access_token, hash_password


class MemoryAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db_path = Path(cls.tmp.name) / "memory_test.db"
        cls.engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        cls.Session = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(cls.engine)

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        ai_service._client = None
        cls.client = TestClient(app)

        db = cls.Session()
        user1 = User(email="memory1@example.com", password_hash=hash_password("test"), nickname="小墨")
        user2 = User(email="memory2@example.com", password_hash=hash_password("test"), nickname="小韵")
        db.add_all([user1, user2])
        db.flush()
        couple = Couple(pairing_code="654321", user1_id=user1.id, user2_id=user2.id, status="active")
        db.add(couple)
        db.flush()
        user1.couple_id = couple.id
        user2.couple_id = couple.id
        db.add(Diary(
            couple_id=couple.id,
            author_id=user1.id,
            title="重庆旅行",
            content="我们第一次一起去了重庆市，在洪崖洞看夜景，非常开心。",
            mood="开心",
        ))
        db.add(Message(
            couple_id=couple.id,
            sender_id=user2.id,
            content="下个月我们一起去看电影吧",
            msg_type="text",
            created_at=datetime.utcnow(),
        ))
        db.commit()
        cls.user1_id = user1.id
        cls.user2_id = user2.id
        cls.headers1 = {"Authorization": f"Bearer {create_access_token(user1.id)}"}
        cls.headers2 = {"Authorization": f"Bearer {create_access_token(user2.id)}"}
        db.close()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.client.close()
        cls.engine.dispose()
        cls.tmp.cleanup()

    def test_01_privacy_opt_in_and_sync(self):
        response = self.client.get("/api/ai/memory/settings", headers=self.headers1)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["enabled"])

        response = self.client.put("/api/ai/memory/settings", headers=self.headers1, json={
            "enabled": True,
            "include_chat": True,
            "include_diary": True,
            "include_album": True,
            "include_anniversary": True,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])

        response = self.client.get("/api/ai/memory", headers=self.headers1)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["total"], 2)

    def test_02_grounded_memory_chat(self):
        response = self.client.post("/api/ai/memory/chat", headers=self.headers1, json={
            "question": "我们第一次去重庆做了什么？",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["answer"])
        self.assertNotIn("[1]", data["answer"])
        self.assertNotIn("sources", data)
        self.assertTrue(data["grounded"])

    def test_03_daily_answer_unlocks_after_both_answer(self):
        question = self.client.get("/api/ai/memory/daily-question/today", headers=self.headers1).json()
        first = self.client.post(
            f"/api/ai/memory/daily-question/{question['id']}/answer",
            headers=self.headers1,
            json={"content": "一起散步聊天"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["both_answered"])
        self.assertEqual(first.json()["answers"], [])

        second = self.client.post(
            f"/api/ai/memory/daily-question/{question['id']}/answer",
            headers=self.headers2,
            json={"content": "一起去吃火锅"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["both_answered"])
        self.assertEqual(len(second.json()["answers"]), 2)

    def test_04_extract_requires_review(self):
        response = self.client.post("/api/ai/memory/extract", headers=self.headers1)
        self.assertEqual(response.status_code, 200)
        pending = self.client.get("/api/ai/memory", headers=self.headers1, params={"status": "pending"})
        self.assertEqual(pending.status_code, 200)
        self.assertGreaterEqual(pending.json()["total"], 1)

    def test_05_memory_report_uses_confirmed_records(self):
        response = self.client.post(
            "/api/ai/memory/report",
            headers=self.headers1,
            params={"days": 365},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data["memory_count"], 1)
        self.assertIn("共同记忆周报", data["content"])

    def test_06_private_memory_is_owner_only_and_preferences_version(self):
        first = self.client.post("/api/ai/memory/manual", headers=self.headers1, json={
            "title": "饮食偏好",
            "content": "我喜欢吃辣",
            "visibility": "private",
            "category": "preference",
        })
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/api/ai/memory/manual", headers=self.headers1, json={
            "title": "饮食偏好",
            "content": "最近胃不舒服，需要少辣",
            "visibility": "private",
            "category": "preference",
        })
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["version"], 2)

        mine = self.client.get(
            "/api/ai/memory", headers=self.headers1, params={"visibility": "private"}
        ).json()
        partner = self.client.get(
            "/api/ai/memory", headers=self.headers2, params={"visibility": "private"}
        ).json()
        self.assertTrue(any(item["content"] == "最近胃不舒服，需要少辣" for item in mine["items"]))
        self.assertFalse(any(item["title"] == "饮食偏好" for item in partner["items"]))

    def test_07_date_plan_uses_only_visible_memory(self):
        response = self.client.post("/api/ai/date-plan", headers=self.headers1, json={
            "city": "重庆",
            "desired_date": "本周六",
            "budget": "300元",
            "duration": "半天",
            "preferences": "想轻松一点",
            "avoid": "少辣",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("约会方案", data["content"])
        self.assertTrue(any(item["title"] == "饮食偏好" for item in data["sources"]))

        partner = self.client.post("/api/ai/date-plan", headers=self.headers2, json={
            "city": "重庆", "duration": "半天"
        })
        self.assertEqual(partner.status_code, 200)
        self.assertFalse(any(item["title"] == "饮食偏好" for item in partner.json()["sources"]))
        history1 = self.client.get("/api/ai/date-plan", headers=self.headers1).json()["items"]
        history2 = self.client.get("/api/ai/date-plan", headers=self.headers2).json()["items"]
        self.assertEqual([item["id"] for item in history1], [data["id"]])
        self.assertEqual([item["id"] for item in history2], [partner.json()["id"]])


if __name__ == "__main__":
    unittest.main()
