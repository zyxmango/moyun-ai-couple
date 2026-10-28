"""用一条真实模型数据验证候选聚合、明确关闭和正式记忆物化。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Couple, MemoryCandidate, MemoryEventHistory, Message, SharedMemory, User
from app.services.ai_service import ai_service
from app.services.memory_service import memory_service


DB_PATH = Path(__file__).resolve().parent / "data" / "memory_pipeline_single_test.db"


def main():
    if not ai_service.available:
        raise RuntimeError("需要可用的在线模型配置")
    if DB_PATH.exists():
        DB_PATH.unlink()
    engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add_all([
            User(id=1, email="pipeline.a@example.test", password_hash="unused", nickname="小墨", couple_id=1),
            User(id=2, email="pipeline.b@example.test", password_hash="unused", nickname="小韵", couple_id=1),
            Couple(id=1, pairing_code="PIPELINE", user1_id=1, user2_id=2, status="active"),
        ])
        started = datetime(2026, 5, 2, 9, 0)
        lines = [
            "2026年5月2日我们一起到武汉了，这次旅行终于开始啦。",
            "下午我们去了东湖绿道，慢慢散步还拍了很多照片。",
            "晚饭一起吃了藕汤，味道很好。",
            "现在旅行结束，我们已经回到家了。",
        ]
        db.add_all([
            Message(
                couple_id=1, sender_id=1 + index % 2, content=content, msg_type="text",
                read_status=True, created_at=started + timedelta(hours=index * 4),
            )
            for index, content in enumerate(lines)
        ])
        db.commit()
        result = memory_service.sync_chat_events(db, 1, max_batches=1)
        candidates = db.query(MemoryCandidate).all()
        memories = db.query(SharedMemory).filter(SharedMemory.source_type == "chat_event").all()
        history = db.query(MemoryEventHistory).all()
        if result["processed_messages"] != 4:
            raise AssertionError(f"同步数量错误：{result}")
        if len(candidates) != 1 or len(memories) != 1:
            raise AssertionError(f"期望一个候选和一条记忆，实际 {len(candidates)} / {len(memories)}")
        memory = memories[0]
        for expected in ("武汉", "东湖绿道", "藕汤"):
            if expected not in f"{memory.title} {memory.content} {memory.location}":
                raise AssertionError(f"正式记忆缺少关键事实：{expected}")
        if memory.lifecycle != "closed" or memory.closure_reason != "explicit_completion":
            raise AssertionError(f"关闭边界错误：{memory.lifecycle} / {memory.closure_reason}")
        if memory.memory_state != "completed":
            raise AssertionError(f"业务状态错误：{memory.memory_state}")
        if len(memory_service._json_ids(memory.source_message_ids)) != 4:
            raise AssertionError("正式记忆没有保留全部四条原始证据")
        facts = memory_service._json_list(memory.facts)
        if not any("藕汤" in str(fact.get("value") or "") for fact in facts):
            raise AssertionError("结构化事实没有保留餐食信息")
        while True:
            embedded = memory_service.ensure_embeddings(db, 1, limit=16)
            if embedded["remaining_embeddings"] == 0:
                break
        sources = memory_service.search(db, 1, "武汉旅行时去了哪里，晚饭吃了什么？", top_k=5, user_id=1)
        if not sources:
            raise AssertionError("语义检索没有召回武汉旅行")
        context = "\n".join(
            f"- 时间：{item['event_date']}；状态：{item['memory_state']}；内容：{item['content']}；"
            f"事实：{json.dumps(item.get('facts', []), ensure_ascii=False)}"
            for item in sources
        )
        answer = ai_service.memory_answer(
            "武汉旅行时去了哪里，晚饭吃了什么？", context, [], strict=True
        )
        for expected in ("东湖绿道", "藕汤"):
            if expected not in answer:
                raise AssertionError(f"最终回答缺少有依据的事实：{expected}；回答={answer}")
        print(json.dumps({
            "model": ai_service.model,
            "sync": result,
            "candidate_count": len(candidates),
            "memory_count": len(memories),
            "history_count": len(history),
            "candidate": {
                "event_key": candidates[0].event_key,
                "event_kind": candidates[0].event_kind,
                "state": candidates[0].state,
                "lifecycle": candidates[0].lifecycle,
                "closure_reason": candidates[0].closure_reason,
                "source_message_ids": memory_service._json_ids(candidates[0].source_message_ids),
            },
            "memory": {
                "title": memory.title, "content": memory.content,
                "facts": facts,
                "state": memory.memory_state, "lifecycle": memory.lifecycle,
                "closure_reason": memory.closure_reason,
                "source_message_ids": memory_service._json_ids(memory.source_message_ids),
            },
            "retrieved_memory_ids": [item["id"] for item in sources],
            "answer": answer,
            "passed": True,
            "database": str(DB_PATH),
        }, ensure_ascii=False, indent=2))
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
