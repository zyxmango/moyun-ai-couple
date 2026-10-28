"""AI 共同记忆端到端 API 测试（不调用外部模型）。"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import (
    Couple, CoupleAISettings, Diary, MemoryCandidate, MemoryEmbeddingBucket,
    MemoryEventHistory, Message, SharedMemory, User,
)
from app.services.ai_service import ai_service
from app.services.memory_service import memory_service
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

    def test_04_chat_is_automatically_organized_as_event(self):
        response = self.client.post("/api/ai/memory/extract", headers=self.headers1)
        self.assertEqual(response.status_code, 200)
        pending = self.client.get("/api/ai/memory", headers=self.headers1, params={"status": "pending"})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["total"], 0)
        events = self.client.get(
            "/api/ai/memory", headers=self.headers1, params={"source_type": "chat_event"}
        ).json()
        self.assertGreaterEqual(events["total"], 1)
        self.assertTrue(events["items"][0]["source_message_ids"])

    def test_04b_cursor_advances_past_noise_without_creating_fragment_memory(self):
        db = self.Session()
        settings = db.query(CoupleAISettings).first()
        old_cursor = settings.last_synced_message_id
        couple_id = settings.couple_id
        db.add_all([
            Message(couple_id=couple_id, sender_id=self.user1_id, content="哈哈", msg_type="text"),
            Message(couple_id=couple_id, sender_id=self.user2_id, content="嗯嗯", msg_type="text"),
        ])
        db.commit()
        newest_id = db.query(Message.id).filter(Message.couple_id == couple_id).order_by(Message.id.desc()).first()[0]
        db.close()

        result = self.client.post("/api/ai/memory/sync", headers=self.headers1).json()
        self.assertGreater(result["last_synced_message_id"], old_cursor)
        self.assertEqual(result["last_synced_message_id"], newest_id)

        db = self.Session()
        fragments = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.content.in_(["哈哈", "嗯嗯"]),
        ).count()
        db.close()
        self.assertEqual(fragments, 0)

    def test_04bb_offline_event_does_not_copy_surrounding_chitchat(self):
        events = ai_service._fallback_memory_events([
            {"id": 1, "content": "早上好，今天也要加油。"},
            {"id": 2, "content": "我不喜欢香菜，点菜时请备注。"},
            {"id": 3, "content": "收到，我晚一点回复你。"},
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_message_ids"], [2])
        self.assertIn("不喜欢香菜", events[0]["summary"])
        self.assertNotIn("早上好", events[0]["summary"])
        self.assertNotIn("晚一点回复", events[0]["summary"])

    def test_04bbb_cancelled_plan_and_missing_fact_are_not_confused(self):
        events = ai_service._fallback_memory_events([
            {"id": 1, "content": "我们原来计划去南极看企鹅。"},
            {"id": 2, "content": "这次不去了，计划取消，暂时不改期。"},
        ])
        self.assertEqual(events[0]["state"], "cancelled")

        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        results = memory_service.search(
            db, couple_id, "我们有没有一起去过南极参加企鹅科考？", top_k=5, user_id=self.user1_id
        )
        db.close()
        self.assertEqual(results, [])

    def test_04bbc_multiple_events_from_same_evidence_get_unique_source_ids(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        message = Message(
            couple_id=couple_id,
            sender_id=self.user1_id,
            content="我们把星河纪念日加入共同提醒，下周还要一起核对日历。",
            msg_type="text",
            created_at=datetime(2040, 6, 8, 20, 0),
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        base = {
            "event_date": "2040-06-08T20:00:00", "event_end": "",
            "location": "", "emotion": "", "tags": [], "importance": 0.7,
            "confidence": 0.9, "source_message_ids": [message.id],
        }
        memory_service._store_chat_event(db, couple_id, {
            **base, "title": "星河纪念日提醒", "summary": "双方已把星河纪念日加入共同提醒。",
            "category": "fact", "state": "completed",
        }, [message])
        memory_service._store_chat_event(db, couple_id, {
            **base, "title": "核对共同日历", "summary": "双方计划下周核对共同日历。",
            "category": "plan", "state": "planned",
        }, [message])
        db.commit()
        rows = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.source_id.like(f"messages-{message.id}-{message.id}-%"),
        ).all()
        db.close()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row.source_id for row in rows}), 2)

    def test_04bbd_long_term_gate_rejects_routine_status(self):
        messages = [
            {"id": 1, "content": "快递已经放进柜子了。"},
            {"id": 2, "content": "2028年5月2日我们去了泉州旅行。"},
        ]
        routine = {
            "title": "快递投柜", "summary": "快递已经放进柜子。", "category": "fact",
            "source_message_ids": [1],
        }
        trip = {
            "title": "泉州旅行", "summary": "两人去了泉州旅行。", "category": "event",
            "source_message_ids": [2],
        }
        self.assertFalse(ai_service._has_long_term_value(routine, messages))
        self.assertTrue(ai_service._has_long_term_value(trip, messages))

    def test_04bbe_fragments_aggregate_before_one_memory_is_materialized(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        event_at = datetime(2042, 5, 2, 10, 0)
        messages = [
            Message(couple_id=couple_id, sender_id=self.user1_id, content="我们到武汉了。", msg_type="text", created_at=event_at),
            Message(couple_id=couple_id, sender_id=self.user2_id, content="下午一起去了东湖绿道。", msg_type="text", created_at=event_at + timedelta(hours=4)),
            Message(couple_id=couple_id, sender_id=self.user1_id, content="晚饭吃了藕汤。", msg_type="text", created_at=event_at + timedelta(hours=9)),
            Message(couple_id=couple_id, sender_id=self.user2_id, content="旅行结束，我们回到家了。", msg_type="text", created_at=event_at + timedelta(hours=14)),
        ]
        db.add_all(messages)
        db.commit()
        for item in messages:
            db.refresh(item)
        fragments = [
            {"title": "抵达武汉", "summary": "两人抵达武汉", "category": "event", "event_kind": "trip",
             "event_key": "trip:武汉", "entities": ["武汉"], "state": "ongoing", "event_date": event_at.isoformat(),
             "confidence": 0.95, "source_message_ids": [messages[0].id]},
            {"title": "游览东湖绿道", "summary": "下午去了东湖绿道", "category": "event", "event_kind": "trip",
             "event_key": "trip:武汉", "entities": ["东湖绿道"], "state": "ongoing", "event_date": event_at.isoformat(),
             "confidence": 0.95, "source_message_ids": [messages[1].id]},
            {"title": "武汉旅行餐食", "summary": "晚饭吃了藕汤", "category": "event", "event_kind": "trip",
             "event_key": "trip:武汉", "entities": ["藕汤"], "state": "ongoing", "event_date": event_at.isoformat(),
             "confidence": 0.95, "source_message_ids": [messages[2].id]},
            {"title": "武汉旅行结束", "summary": "旅行结束并回家", "category": "event", "event_kind": "trip",
             "event_key": "trip:武汉", "entities": ["武汉"], "state": "completed", "event_date": event_at.isoformat(),
             "confidence": 0.95, "source_message_ids": [messages[3].id]},
        ]
        candidate = None
        for fragment in fragments:
            candidate, _ = memory_service._merge_candidate_fragment(db, couple_id, fragment, messages)
        original = ai_service.summarize_memory_candidate
        ai_service.summarize_memory_candidate = Mock(return_value={
            "title": "武汉旅行", "summary": "两人到武汉旅行，去了东湖绿道，晚饭吃了藕汤，之后回到家。",
            "location": "武汉·东湖绿道", "emotion": "开心", "tags": ["旅行"], "importance": 0.8,
        })
        try:
            self.assertTrue(memory_service._materialize_candidate(db, candidate))
            db.commit()
        finally:
            ai_service.summarize_memory_candidate = original
        db.refresh(candidate)
        memory = db.query(SharedMemory).filter(SharedMemory.id == candidate.memory_id).one()
        self.assertEqual(db.query(MemoryCandidate).filter(MemoryCandidate.event_key == candidate.event_key).count(), 1)
        self.assertEqual(memory.lifecycle, "closed")
        self.assertEqual(memory.closure_reason, "explicit_completion")
        self.assertEqual(memory.memory_state, "completed")
        self.assertIn("东湖绿道", memory.content)
        self.assertIn("藕汤", memory.content)
        self.assertEqual(set(memory_service._json_ids(memory.source_message_ids)), {item.id for item in messages})
        self.assertEqual(db.query(MemoryEventHistory).filter(MemoryEventHistory.memory_id == memory.id).count(), 1)
        db.close()

    def test_04c_failed_extraction_keeps_cursor_for_retry(self):
        db = self.Session()
        settings = db.query(CoupleAISettings).first()
        old_cursor = settings.last_synced_message_id
        db.add(Message(
            couple_id=settings.couple_id,
            sender_id=self.user1_id,
            content="我们计划明年一起去冰岛旅行",
            msg_type="text",
        ))
        db.commit()
        original_client = ai_service._client
        failing_client = Mock()
        failing_client.chat.completions.create.side_effect = RuntimeError("temporary model error")
        ai_service._client = failing_client
        try:
            result = memory_service.sync_chat_events(db, settings.couple_id, max_batches=1)
            db.refresh(settings)
            self.assertEqual(result["processed_messages"], 0)
            self.assertEqual(settings.last_synced_message_id, old_cursor)
            self.assertIn("temporary model error", settings.sync_error)
        finally:
            ai_service._client = original_client
            db.close()

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

    def test_08_old_relevant_memory_is_not_removed_by_a_recent_window(self):
        db = self.Session()
        couple_id = db.query(CoupleAISettings.couple_id).first()[0]
        old_target = SharedMemory(
            couple_id=couple_id,
            source_type="manual",
            source_id="old-aurora-memory",
            title="冰岛极光旅行",
            content="我们第一次去冰岛时在维克附近看到了极光",
            event_date=datetime.utcnow() - timedelta(days=1500),
            status="confirmed",
            visibility="shared",
            category="event",
            is_active=True,
        )
        db.add(old_target)
        for index in range(1501):
            db.add(SharedMemory(
                couple_id=couple_id,
                source_type="manual",
                source_id=f"recent-noise-{index}",
                title=f"普通日常记录{index}",
                content="今天完成了普通的生活安排",
                event_date=datetime.utcnow() - timedelta(minutes=index),
                status="confirmed",
                visibility="shared",
                category="event",
                is_active=True,
            ))
        db.commit()
        results = memory_service.search(db, couple_id, "第一次去冰岛在哪里看到极光？", top_k=5, user_id=self.user1_id)
        self.assertTrue(any(item["source_id"] == "old-aurora-memory" for item in results))
        db.refresh(old_target)
        self.assertTrue(old_target.embedding_b64)
        self.assertEqual(
            db.query(MemoryEmbeddingBucket).filter(MemoryEmbeddingBucket.memory_id == old_target.id).count(),
            memory_service.LSH_TABLES,
        )

        # 超过精确扫描阈值后，仍应从持久化 LSH 语义桶召回旧事件。
        for index in range(1600):
            db.add(SharedMemory(
                couple_id=couple_id,
                source_type="manual",
                source_id=f"more-noise-{index}",
                title=f"更多日常记录{index}",
                content="整理房间并完成普通生活安排",
                event_date=datetime.utcnow(),
                status="confirmed",
                visibility="shared",
                category="event",
                is_active=True,
            ))
        db.commit()
        indexed_results = memory_service.search(
            db, couple_id, "第一次去冰岛在哪里看到极光？", top_k=5, user_id=self.user1_id
        )
        db.close()
        self.assertTrue(any(item["source_id"] == "old-aurora-memory" for item in indexed_results))


if __name__ == "__main__":
    unittest.main()
