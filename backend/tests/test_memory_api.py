"""AI 共同记忆端到端 API 测试（不调用外部模型）。"""
import json
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
    MemoryEventHistory, MemorySyncJob, MemorySyncRun, Message, SharedMemory, User,
)
from app.services.ai_service import ai_service
from app.services.memory_service import memory_service
from app.services.memory_jobs import enqueue_memory_sync, claim_next_job, execute_claimed_job
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

    def test_00_model_score_labels_are_normalized(self):
        self.assertEqual(ai_service._unit_float("medium"), 0.5)
        self.assertEqual(ai_service._unit_float("高"), 0.8)
        self.assertEqual(ai_service._unit_float("invalid", 0.6), 0.6)
        self.assertEqual(ai_service._unit_float(2), 1.0)

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

        response = self.client.post("/api/ai/memory/sync", headers=self.headers1)
        self.assertEqual(response.status_code, 200)

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
        couple_id = settings.couple_id
        old_cursor = settings.last_synced_message_id
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

    def test_04bbba_uncovered_meal_is_attached_to_trip_facts(self):
        messages = [
            {"id": 1, "created_at": "2041-05-02T09:00:00", "content": "我们到武汉了，旅行开始。"},
            {"id": 2, "created_at": "2041-05-02T13:00:00", "content": "下午去了东湖绿道散步。"},
            {"id": 3, "created_at": "2041-05-02T17:00:00", "content": "晚饭吃了藕汤，味道很好。"},
        ]
        event = {
            "event_kind": "trip", "source_message_ids": [1, 2],
            "facts": [{"type": "activity", "value": "去了东湖绿道", "source_message_ids": [2]}],
        }
        result = ai_service._attach_uncovered_context_facts([event], messages)
        self.assertIn(3, result[0]["source_message_ids"])
        self.assertTrue(any(fact["type"] == "meal" and "藕汤" in fact["value"] for fact in result[0]["facts"]))

    def test_04bbbb_malformed_model_json_retries_once(self):
        invalid = Mock()
        invalid.choices = [Mock(message=Mock(content='[{"title":"偏好" "summary":"喜欢咖啡"}]'))]
        valid = Mock()
        valid.choices = [Mock(message=Mock(content=json.dumps([{
            "title": "咖啡偏好", "summary": "现在明确选择无糖咖啡。",
            "category": "preference", "event_kind": "preference",
            "event_key": "preference:咖啡", "entities": ["咖啡"], "state": "ongoing",
            "event_date": "2041-06-01T10:00:00", "confidence": 0.9,
            "source_message_ids": [1], "facts": [{
                "type": "current_preference", "value": "现在选择无糖咖啡", "source_message_ids": [1],
            }],
        }], ensure_ascii=False)))]
        client = Mock()
        client.chat.completions.create.side_effect = [invalid, valid]
        original_client = ai_service._client
        ai_service._client = client
        try:
            events = ai_service.extract_memory_events([{
                "id": 1, "sender_id": 1, "created_at": "2041-06-01T10:00:00",
                "content": "请记住我现在明确选择无糖咖啡。",
            }])
        finally:
            ai_service._client = original_client
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertEqual(events[0]["facts"][0]["type"], "current_preference")

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

    def test_04bbf_structured_facts_state_and_date_are_deterministic(self):
        state, lifecycle, reason = memory_service._candidate_boundary(
            "activity", "下午去了东湖绿道散步拍照。", "completed"
        )
        self.assertEqual((state, lifecycle, reason), ("completed", "closed", "explicit_completion"))

        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        changed_at = datetime(2043, 8, 20, 18, 0)
        messages = [
            Message(
                couple_id=couple_id, sender_id=self.user1_id,
                content="以前早餐喝豆浆，不过现在改成热牛奶。", msg_type="text", created_at=changed_at,
            ),
            Message(
                couple_id=couple_id, sender_id=self.user2_id,
                content="以后早餐就按热牛奶准备。", msg_type="text", created_at=changed_at + timedelta(minutes=5),
            ),
        ]
        db.add_all(messages)
        db.commit()
        for item in messages:
            db.refresh(item)
        event = {
            "title": "早餐饮品偏好变化", "summary": "早餐饮品从豆浆改为热牛奶。",
            "category": "preference", "event_kind": "preference", "event_key": "preference:早餐饮品",
            "entities": ["早餐饮品", "豆浆", "热牛奶"], "state": "ongoing",
            # 模拟模型给出一个与证据时间明显冲突的日期，程序应以消息时间为准。
            "event_date": "2012-12-09T18:00:00", "confidence": 0.95,
            "source_message_ids": [item.id for item in messages],
            "facts": [
                {"type": "previous_preference", "value": "早餐以前喝豆浆", "source_message_ids": [messages[0].id]},
                {"type": "current_preference", "value": "早餐现在改为热牛奶", "source_message_ids": [messages[0].id, messages[1].id]},
            ],
        }
        candidate, _ = memory_service._merge_candidate_fragment(db, couple_id, event, messages)
        self.assertEqual(candidate.event_date.date(), changed_at.date())
        self.assertEqual(candidate.state, "ongoing")
        self.assertTrue(memory_service._materialize_candidate(db, candidate))
        db.commit()
        memory = db.query(SharedMemory).filter(SharedMemory.id == candidate.memory_id).one()
        facts = memory_service._json_list(memory.facts)
        self.assertEqual([fact["type"] for fact in facts], ["previous_preference", "current_preference"])
        self.assertIn("热牛奶", memory.content)
        self.assertEqual(memory.valid_from.date(), changed_at.date())
        db.close()

    def test_04bbg_same_place_on_different_dates_stays_separate(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        messages = []
        for year in (2044, 2045):
            item = Message(
                couple_id=couple_id, sender_id=self.user1_id,
                content=f"{year}年5月2日我们去了武汉。", msg_type="text",
                created_at=datetime(year, 5, 2, 12, 0),
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            messages.append(item)
            candidate, _ = memory_service._merge_candidate_fragment(db, couple_id, {
                "title": "武汉旅行", "summary": f"{year}年去了武汉。", "category": "event",
                "event_kind": "trip", "event_key": "trip:武汉", "entities": ["武汉"],
                "state": "completed", "event_date": item.created_at.isoformat(),
                "confidence": 0.95, "source_message_ids": [item.id],
            }, [item])
            self.assertEqual(candidate.event_date.date(), item.created_at.date())
        db.commit()
        keys = [row[0] for row in db.query(MemoryCandidate.event_key).filter(
            MemoryCandidate.couple_id == couple_id,
            MemoryCandidate.event_key.like("trip:武汉:%"),
        ).all()]
        db.close()
        self.assertIn("trip:武汉:2044-05-02", keys)
        self.assertIn("trip:武汉:2045-05-02", keys)

    def test_04bbh_different_preference_topics_do_not_merge(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        created_at = datetime(2046, 6, 1, 12, 0)
        rows = []
        for index, (topic, value) in enumerate((("咖啡甜度", "无糖"), ("火锅辣度", "微辣"))):
            message = Message(
                couple_id=couple_id, sender_id=self.user1_id,
                content=f"请记住我现在的{topic}偏好是{value}。", msg_type="text",
                created_at=created_at + timedelta(minutes=index),
            )
            db.add(message)
            db.commit()
            db.refresh(message)
            candidate, _ = memory_service._merge_candidate_fragment(db, couple_id, {
                "title": f"{topic}偏好", "summary": f"当前{topic}选择{value}",
                "category": "preference", "event_kind": "preference",
                "event_key": f"preference:{topic}", "entities": ["用户1", "偏好", topic, value],
                "state": "ongoing", "event_date": message.created_at.isoformat(),
                "confidence": 0.95, "source_message_ids": [message.id],
                "facts": [{"type": "current_preference", "value": f"{topic}={value}", "source_message_ids": [message.id]}],
            }, [message])
            rows.append(candidate)
        db.commit()
        self.assertNotEqual(rows[0].id, rows[1].id)
        self.assertNotEqual(rows[0].event_key, rows[1].event_key)
        db.close()

    def test_04bbha_online_empty_result_never_uses_batch_wide_fallback(self):
        empty = Mock()
        empty.choices = [Mock(message=Mock(content="[]"))]
        client = Mock()
        client.chat.completions.create.side_effect = [empty, empty]
        original_client = ai_service._client
        ai_service._client = client
        try:
            events = ai_service.extract_memory_events([
                {"id": 1, "sender_id": 1, "created_at": "2047-01-01T10:00:00", "content": "我们到了武汉。"},
                {"id": 2, "sender_id": 1, "created_at": "2047-02-01T10:00:00", "content": "以后不要按跑步准备。"},
                {"id": 3, "sender_id": 1, "created_at": "2047-03-01T10:00:00", "content": "学习双人舞取消了。"},
            ])
        finally:
            ai_service._client = original_client
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertEqual(events, [])

    def test_04bbhb_uncovered_fact_requires_same_day_and_unique_target(self):
        cross_day = ai_service._attach_uncovered_context_facts([{
            "event_kind": "trip", "event_key": "trip:武汉", "source_message_ids": [1],
            "facts": [{"type": "destination", "value": "抵达武汉", "source_message_ids": [1]}],
        }], [
            {"id": 1, "created_at": "2047-05-01T10:00:00", "content": "我们抵达武汉。"},
            {"id": 2, "created_at": "2047-05-02T18:00:00", "content": "晚饭吃了藕汤。"},
        ])
        self.assertEqual(cross_day[0]["source_message_ids"], [1])

        ambiguous = ai_service._attach_uncovered_context_facts([
            {
                "event_kind": "trip", "event_key": "trip:武汉", "source_message_ids": [10],
                "facts": [{"type": "destination", "value": "武汉", "source_message_ids": [10]}],
            },
            {
                "event_kind": "trip", "event_key": "trip:南京", "source_message_ids": [12],
                "facts": [{"type": "destination", "value": "南京", "source_message_ids": [12]}],
            },
        ], [
            {"id": 10, "created_at": "2047-06-01T10:00:00", "content": "抵达武汉。"},
            {"id": 11, "created_at": "2047-06-01T18:00:00", "content": "晚饭吃了面。"},
            {"id": 12, "created_at": "2047-06-01T20:00:00", "content": "抵达南京。"},
        ])
        self.assertNotIn(11, ambiguous[0]["source_message_ids"])
        self.assertNotIn(11, ambiguous[1]["source_message_ids"])

        preference = ai_service._attach_uncovered_context_facts([{
            "event_kind": "preference", "event_key": "preference:早餐饮品",
            "source_message_ids": [20], "facts": [],
        }], [{
            "id": 20, "created_at": "2047-07-01T08:00:00",
            "content": "以前早餐喝豆浆，现在改成热牛奶。",
        }])[0]
        self.assertEqual(
            {fact["type"] for fact in preference["facts"]},
            {"previous_preference", "current_preference"},
        )

        long_gap = ai_service._attach_uncovered_context_facts([{
            "event_kind": "trip", "event_key": "trip:武汉", "source_message_ids": [30],
            "facts": [{"type": "destination", "value": "抵达武汉", "source_message_ids": [30]}],
        }], [
            {"id": 30, "created_at": "2047-08-01T09:00:00", "content": "我们到武汉啦。"},
            {"id": 31, "created_at": "2047-08-01T09:05:00", "content": "我到家以后再给你发消息。"},
            {"id": 45, "created_at": "2047-08-01T18:00:00", "content": "晚上吃的是藕汤，我觉得很香。"},
            {"id": 46, "created_at": "2047-08-01T18:05:00", "content": "晚饭先不用等我。"},
        ])[0]
        self.assertIn(45, long_gap["source_message_ids"])
        self.assertNotIn(31, long_gap["source_message_ids"])
        self.assertNotIn(46, long_gap["source_message_ids"])
        self.assertTrue(any(fact["type"] == "meal" and "藕汤" in fact["value"] for fact in long_gap["facts"]))

    def test_04bbhc_routine_event_key_cannot_merge_across_dates(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        candidates = []
        for index, created_at in enumerate((datetime(2048, 1, 1, 10), datetime(2048, 3, 1, 10))):
            message = Message(
                couple_id=couple_id, sender_id=self.user1_id,
                content="我到家以后再给你发消息。", msg_type="text", created_at=created_at,
            )
            db.add(message)
            db.commit()
            db.refresh(message)
            candidate, _ = memory_service._merge_candidate_fragment(db, couple_id, {
                "title": "我到家以后再给你发消息", "summary": "计划稍后联系。",
                "category": "plan", "event_kind": "plan",
                "event_key": "我到家以后再给你发消息", "entities": [],
                "state": "planned", "event_date": created_at.isoformat(),
                "confidence": 0.8, "source_message_ids": [message.id],
            }, [message])
            candidates.append(candidate)
        db.commit()
        self.assertNotEqual(candidates[0].id, candidates[1].id)
        self.assertNotEqual(candidates[0].event_key, candidates[1].event_key)
        db.close()

    def test_04bbhd_same_preference_topic_updates_one_candidate(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        candidates = []
        for index, (value, created_at) in enumerate((
            ("半糖拿铁", datetime(2049, 1, 1, 10)),
            ("无糖燕麦拿铁", datetime(2049, 5, 1, 10)),
        )):
            message = Message(
                couple_id=couple_id, sender_id=self.user1_id,
                content=f"我现在的咖啡甜度选择{value}。", msg_type="text", created_at=created_at,
            )
            db.add(message)
            db.commit()
            db.refresh(message)
            candidate, _ = memory_service._merge_candidate_fragment(db, couple_id, {
                "title": "咖啡甜度偏好", "summary": f"咖啡甜度选择{value}",
                "category": "preference", "event_kind": "preference",
                "event_key": "preference:咖啡甜度", "entities": ["咖啡甜度", value],
                "state": "ongoing", "event_date": created_at.isoformat(),
                "confidence": 0.9, "source_message_ids": [message.id],
                "facts": [{"type": "current_preference", "value": value, "source_message_ids": [message.id]}],
            }, [message])
            candidates.append(candidate)
        db.commit()
        self.assertEqual(candidates[0].id, candidates[1].id)
        facts = memory_service._json_list(candidates[1].facts)
        current = [fact for fact in facts if fact["type"] == "current_preference"]
        previous = [fact for fact in facts if fact["type"] == "previous_preference"]
        self.assertEqual(len(current), 1)
        self.assertIn("无糖燕麦拿铁", current[0]["value"])
        self.assertGreaterEqual(len(previous), 1)
        db.close()

    def test_04bbhe_same_day_overlapping_plan_fragments_merge(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        created_at = datetime(2050, 6, 1, 18)
        messages = [
            Message(couple_id=couple_id, sender_id=self.user1_id, content="原来约好报名陶艺课。",
                    msg_type="text", created_at=created_at),
            Message(couple_id=couple_id, sender_id=self.user2_id, content="临时工作时间冲突。",
                    msg_type="text", created_at=created_at + timedelta(minutes=2)),
            Message(couple_id=couple_id, sender_id=self.user1_id, content="这次报名陶艺课取消了。",
                    msg_type="text", created_at=created_at + timedelta(minutes=4)),
        ]
        db.add_all(messages)
        db.commit()
        for item in messages:
            db.refresh(item)
        first, _ = memory_service._merge_candidate_fragment(db, couple_id, {
            "title": "报名陶艺课计划取消", "summary": "报名陶艺课因时间冲突取消。",
            "category": "plan", "event_kind": "plan", "event_key": "plan:报名陶艺课:205006",
            "entities": ["陶艺课"], "state": "cancelled", "event_date": created_at.isoformat(),
            "confidence": 0.95, "source_message_ids": [item.id for item in messages],
        }, messages)
        second, _ = memory_service._merge_candidate_fragment(db, couple_id, {
            "title": "陶艺课报名取消", "summary": "陶艺课报名已经取消。",
            "category": "plan", "event_kind": "plan", "event_key": "plan:陶艺课报名",
            "entities": ["陶艺课"], "state": "cancelled", "event_date": created_at.isoformat(),
            "confidence": 0.9, "source_message_ids": [messages[-1].id],
        }, messages)
        db.commit()
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            db.query(MemoryCandidate).filter(
                MemoryCandidate.couple_id == couple_id,
                MemoryCandidate.event_date >= created_at,
            ).count(),
            1,
        )
        db.close()

    def test_04bbhf_qwen_non_thinking_and_local_candidate_summary(self):
        response = Mock()
        response.choices = [Mock(message=Mock(content=json.dumps([{
            "title": "哈尔滨看雪计划取消", "summary": "哈尔滨看雪计划因工作冲突取消。",
            "category": "plan", "event_kind": "trip", "event_key": "plan:哈尔滨看雪",
            "entities": ["哈尔滨"], "state": "cancelled", "event_date": "2051-01-01",
            "location": "哈尔滨", "emotion": "", "tags": ["计划"], "importance": 0.8,
            "confidence": 0.95, "source_message_ids": [1, 2, 3],
            "facts": [
                {"type": "plan_intent", "value": "去哈尔滨看雪", "source_message_ids": [1]},
                {"type": "cancellation_reason", "value": "临时工作时间冲突", "source_message_ids": [2]},
                {"type": "plan_status", "value": "已经取消", "source_message_ids": [3]},
            ],
        }], ensure_ascii=False)))]
        client = Mock()
        client.chat.completions.create.return_value = response
        original = (
            ai_service._client, ai_service.api_base, ai_service.model,
            ai_service.enable_thinking, ai_service.memory_summary_with_model,
        )
        ai_service._client = client
        ai_service.api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ai_service.model = "qwen3.8-max"
        ai_service.enable_thinking = False
        ai_service.memory_summary_with_model = False
        try:
            events = ai_service.extract_memory_events([
                {"id": 1, "sender_id": 1, "created_at": "2051-01-01T10:00:00", "content": "约好去哈尔滨看雪。"},
                {"id": 2, "sender_id": 2, "created_at": "2051-01-01T10:02:00", "content": "临时工作时间冲突。"},
                {"id": 3, "sender_id": 1, "created_at": "2051-01-01T10:04:00", "content": "哈尔滨看雪已经取消。"},
            ])
            summary = ai_service.summarize_memory_candidate({
                "event_kind": "plan", "title_hint": "plan:哈尔滨看雪",
                "fragments": [{"title": "哈尔滨看雪计划取消", "summary": "计划因工作冲突取消。"}],
                "facts": [{"type": "plan_status", "value": "已经取消"}],
            }, [])
        finally:
            (
                ai_service._client, ai_service.api_base, ai_service.model,
                ai_service.enable_thinking, ai_service.memory_summary_with_model,
            ) = original
        self.assertEqual(events[0]["event_kind"], "plan")
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["extra_body"],
            {"enable_thinking": False},
        )
        self.assertEqual(summary["title"], "哈尔滨看雪计划取消")
        self.assertIn("工作冲突", summary["summary"])

    def test_04bbi_empty_context_uses_deterministic_abstention(self):
        answer = ai_service.memory_answer("我们约好移居火星了吗？", "没有找到相关共同记忆。", [], strict=True)
        self.assertEqual(answer, "目前没有找到相关记录，所以我无法确认这件事。")

    def test_04bbj_answer_removes_unsupported_absence_and_unsolicited_advice(self):
        answer = ai_service._sanitize_memory_answer(
            "计划已经取消，暂时没有新日期。后来也没再提过重新计划。"
            "如果现在还想去，可以重新商量一个日期。",
            "之前的计划现在是什么状态？",
        )
        self.assertIn("计划已经取消", answer)
        self.assertIn("后续情况，目前无法确认", answer)
        self.assertNotIn("没再提过", answer)
        self.assertNotIn("重新商量", answer)

    def test_04bbk_routine_notifications_are_never_memory_facts(self):
        self.assertTrue(ai_service._is_routine_context("我到家以后再给你发消息。"))
        self.assertTrue(ai_service._is_routine_context("晚饭先不用等我！"))
        self.assertFalse(ai_service._is_routine_context("以后忙时发一句简短说明。"))

    def test_04bbl_missing_fact_slots_use_one_targeted_batch_retry(self):
        response = Mock()
        response.choices = [Mock(message=Mock(content=json.dumps([{
            "event_index": 0,
            "facts": [{
                "type": "meal", "value": "晚上吃的是藕汤",
                "occurred_at": "2050-01-01T18:00:00", "source_message_ids": [3],
            }],
        }], ensure_ascii=False)))]
        client = Mock()
        client.chat.completions.create.return_value = response
        original_client = ai_service._client
        ai_service._client = client
        try:
            events = ai_service._verify_fact_completeness([{
                "event_kind": "trip", "event_key": "trip:武汉", "source_message_ids": [1, 2],
                "facts": [
                    {"type": "destination", "value": "抵达武汉", "source_message_ids": [1]},
                    {"type": "activity", "value": "去了东湖绿道", "source_message_ids": [2]},
                ],
            }], [
                {"id": 1, "created_at": "2050-01-01T09:00:00", "content": "我们抵达武汉。"},
                {"id": 2, "created_at": "2050-01-01T13:00:00", "content": "下午去了东湖绿道。"},
                {"id": 3, "created_at": "2050-01-01T18:00:00", "content": "晚上吃的是藕汤。"},
            ])
        finally:
            ai_service._client = original_client
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertTrue(any(fact["type"] == "meal" and "藕汤" in fact["value"] for fact in events[0]["facts"]))
        self.assertNotIn("missing_fact_slots", events[0])

    def test_04bbm_incoherent_cross_date_event_is_split(self):
        events = ai_service._split_incoherent_events([{
            "title": "错误合并旅行", "event_kind": "trip", "event_key": "trip:旅行",
            "source_message_ids": [1, 2],
            "facts": [
                {"type": "destination", "value": "武汉", "source_message_ids": [1]},
                {"type": "destination", "value": "南京", "source_message_ids": [2]},
            ],
        }], [
            {"id": 1, "created_at": "2050-01-01T09:00:00", "content": "抵达武汉。"},
            {"id": 2, "created_at": "2050-04-01T09:00:00", "content": "抵达南京。"},
        ])
        self.assertEqual(len(events), 2)
        self.assertEqual({tuple(event["source_message_ids"]) for event in events}, {(1,), (2,)})
        self.assertNotEqual(events[0]["event_key"], events[1]["event_key"])

    def test_04bbn_conflict_answer_preserves_agreement_verbatim(self):
        context = (
            "- 事件时间：2050-01-01；状态：completed；类型：倒垃圾冲突；内容：已经和好；"
            "已确认事实：conflict_reason=忘记倒垃圾；resolution=互相道歉并和好；"
            "agreement=列了家务轮值表"
        )
        answer = ai_service._deterministic_conflict_answer("忘记倒垃圾闹矛盾后，我们怎么和好的？", context)
        self.assertIn("忘记倒垃圾", answer)
        self.assertIn("互相道歉并和好", answer)
        self.assertIn("最后约定：列了家务轮值表", answer)

    def test_04bbo_fact_subject_and_event_interval_are_preserved(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        started = datetime(2052, 2, 1, 20, 0)
        resolved = started + timedelta(hours=2)
        messages = [
            Message(couple_id=couple_id, sender_id=self.user1_id, content="我因为你忘记倒垃圾很生气。",
                    msg_type="text", created_at=started),
            Message(couple_id=couple_id, sender_id=self.user2_id, content="我道歉了，我们说开并和好了。",
                    msg_type="text", created_at=resolved),
        ]
        db.add_all(messages)
        db.commit()
        for item in messages:
            db.refresh(item)
        candidate, _ = memory_service._merge_candidate_fragment(db, couple_id, {
            "title": "倒垃圾冲突", "summary": "双方因倒垃圾争执后和好。",
            "category": "event", "event_kind": "conflict", "event_key": "conflict:倒垃圾",
            "entities": ["倒垃圾"], "state": "completed", "started_at": started.isoformat(),
            "resolved_at": resolved.isoformat(), "confidence": 0.95,
            "source_message_ids": [item.id for item in messages],
            "facts": [
                {"type": "conflict_reason", "value": "忘记倒垃圾", "subject_user_id": self.user1_id,
                 "source_message_ids": [messages[0].id]},
                {"type": "resolution", "value": "道歉并说开和好", "subject_user_id": self.user2_id,
                 "source_message_ids": [messages[1].id]},
            ],
        }, messages)
        facts = memory_service._json_list(candidate.facts)
        self.assertEqual(facts[0]["subject_user_id"], self.user1_id)
        self.assertEqual(facts[1]["subject_user_id"], self.user2_id)
        self.assertEqual(facts[0]["asserted_by_user_id"], self.user1_id)
        self.assertEqual(facts[1]["asserted_by_user_id"], self.user2_id)
        self.assertEqual(candidate.started_at, started)
        self.assertEqual(candidate.resolved_at, resolved)
        db.close()

    def test_04bbp_structured_answer_keeps_subject_and_exact_values(self):
        context = (
            f"- 事件时间：2052-03-01；状态：ongoing；类型：咖啡偏好；内容：偏好变化；"
            f"已确认事实：previous_preference@{self.user1_id}=半糖拿铁；"
            f"current_preference@{self.user1_id}=无糖燕麦拿铁；"
            "current_preference=以后不要再按半糖拿铁准备"
        )
        answer = ai_service.memory_answer("我现在喜欢什么咖啡？", context, viewer_user_id=self.user1_id)
        self.assertIn("你当前的偏好", answer)
        self.assertIn("无糖燕麦拿铁", answer)
        self.assertIn("半糖拿铁", answer)

    def test_04bbq_evidence_is_visible_and_forgotten_memory_stays_inactive(self):
        db = self.Session()
        couple_id = db.query(User.couple_id).filter(User.id == self.user1_id).scalar()
        message = Message(
            couple_id=couple_id, sender_id=self.user1_id, content="请记住我现在只喝无糖咖啡。",
            msg_type="text", created_at=datetime(2052, 4, 1, 9, 0),
        )
        db.add(message)
        db.flush()
        memory = SharedMemory(
            couple_id=couple_id, source_type="chat_event", source_id=f"forget-{message.id}",
            title="咖啡偏好", content="只喝无糖咖啡", event_date=message.created_at,
            started_at=message.created_at, status="confirmed", visibility="shared", category="preference",
            source_message_ids=json.dumps([message.id]), is_active=True,
        )
        db.add(memory)
        db.commit()
        memory_id = memory.id
        message_id = message.id
        db.close()

        evidence = self.client.get(f"/api/ai/memory/{memory_id}/evidence", headers=self.headers1)
        self.assertEqual(evidence.status_code, 200)
        self.assertEqual(evidence.json()["items"][0]["sender_nickname"], "小墨")
        self.assertIn("无糖咖啡", evidence.json()["items"][0]["content"])

        forgotten = self.client.delete(f"/api/ai/memory/{memory_id}", headers=self.headers1)
        self.assertEqual(forgotten.status_code, 200)
        db = self.Session()
        row = db.query(SharedMemory).filter(SharedMemory.id == memory_id).one()
        self.assertFalse(row.is_active)
        self.assertIsNotNone(row.forgotten_at)
        candidate = MemoryCandidate(
            couple_id=couple_id, event_key="preference:无糖咖啡", event_kind="preference",
            category="preference", source_message_ids=json.dumps([message_id]), memory_id=memory_id,
        )
        db.add(candidate)
        db.commit()
        summarize = ai_service.summarize_memory_candidate
        ai_service.summarize_memory_candidate = Mock(side_effect=AssertionError("忘记后不应重新调用模型整理"))
        try:
            self.assertFalse(memory_service._materialize_candidate(db, candidate))
        finally:
            ai_service.summarize_memory_candidate = summarize
        db.close()
        self.assertEqual(
            self.client.get(f"/api/ai/memory/{memory_id}/evidence", headers=self.headers1).status_code,
            404,
        )

    def test_04bbr_persistent_worker_queue_is_idempotent_and_records_metrics(self):
        db = self.Session()
        settings = db.query(CoupleAISettings).first()
        couple_id = settings.couple_id
        db.add(Message(
            couple_id=couple_id, sender_id=self.user1_id,
            content="请记住我们计划下个月去看新的摄影展。", msg_type="text",
        ))
        db.commit()
        enqueue_memory_sync(db, couple_id)
        enqueue_memory_sync(db, couple_id)
        db.commit()
        self.assertEqual(db.query(MemorySyncJob).filter(MemorySyncJob.couple_id == couple_id).count(), 1)
        self.assertEqual(claim_next_job(db, "test-worker-1"), couple_id)
        self.assertIsNone(claim_next_job(db, "test-worker-2"))
        db.close()

        result = execute_claimed_job(couple_id, "test-worker-1", session_factory=self.Session)
        self.assertGreaterEqual(result["processed_messages"], 1)
        db = self.Session()
        run = db.query(MemorySyncRun).filter(MemorySyncRun.couple_id == couple_id).order_by(
            MemorySyncRun.id.desc()
        ).first()
        self.assertEqual(run.status, "success")
        self.assertGreaterEqual(run.processed_messages, 1)
        self.assertGreaterEqual(run.duration_ms, 0)
        db.close()

    def test_04bbs_admin_memory_health_is_aggregate_only(self):
        db = self.Session()
        user = db.query(User).filter(User.id == self.user1_id).one()
        user.is_admin = True
        db.commit()
        db.close()
        try:
            response = self.client.get("/api/admin/memory-health", headers=self.headers1)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("message_lag_total", payload)
            self.assertIn("failure_rate", payload["last_24h"])
            self.assertIn("estimated_cost_usd", payload["last_24h"])
            self.assertNotIn("content", json.dumps(payload, ensure_ascii=False).lower())
        finally:
            db = self.Session()
            db.query(User).filter(User.id == self.user1_id).update({"is_admin": False})
            db.commit()
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
