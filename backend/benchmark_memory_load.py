"""使用真实事件模板在临时库验证 4,000 条持久化语义记忆检索。"""
import json
import tempfile
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, SessionLocal
from app.models import MemoryEmbeddingBucket, SharedMemory
from app.services.ai_service import ai_service
from app.services.memory_service import memory_service


TARGET_COUNT = 4_000
CASES = (
    ("武汉东湖旅行", "武汉东湖"),
    ("不喜欢香菜", "香菜"),
    ("冷静十分钟", "冷静十分钟"),
    ("青岛住宿六百元", "六百元"),
    ("番茄牛腩", "番茄牛腩"),
)


def main():
    source_db = SessionLocal()
    try:
        templates = source_db.query(SharedMemory).filter(
            SharedMemory.couple_id == 1,
            SharedMemory.status == "confirmed",
            SharedMemory.is_active.is_(True),
        ).all()
        source_rows = [{
            "title": row.title,
            "content": row.content,
            "event_date": row.event_date,
            "location": row.location,
            "emotion": row.emotion,
            "tags": row.tags,
            "importance": row.importance,
            "visibility": row.visibility,
            "category": row.category,
            "memory_state": row.memory_state,
            "confidence": row.confidence,
        } for row in templates]
    finally:
        source_db.close()
    if not source_rows:
        raise SystemExit("no active memories available")

    # 压测固定使用可复现的本地语义向量，不消耗在线模型额度。
    ai_service._client = None
    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "memory-load.db"
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.bulk_save_objects([
                SharedMemory(
                    couple_id=1,
                    source_type="load_test",
                    source_id=f"memory-{index}",
                    status="confirmed",
                    is_active=True,
                    **source_rows[index % len(source_rows)],
                )
                for index in range(TARGET_COUNT)
            ])
            db.commit()

            index_started = time.perf_counter()
            embedded = 0
            while True:
                result = memory_service.ensure_embeddings(db, 1, limit=512)
                embedded += result["embedded"]
                if result["remaining_embeddings"] == 0:
                    break
            index_ms = (time.perf_counter() - index_started) * 1000

            cases = []
            for question, expected in CASES:
                started = time.perf_counter()
                results = memory_service.search(db, 1, question, top_k=5, user_id=1)
                elapsed_ms = (time.perf_counter() - started) * 1000
                texts = [f"{item['title']} {item['content']}" for item in results]
                cases.append({
                    "question": question,
                    "expected": expected,
                    "hit": any(expected in text for text in texts),
                    "latency_ms": round(elapsed_ms, 2),
                    "top_title": results[0]["title"] if results else None,
                })

            print(json.dumps({
                "memories": TARGET_COUNT,
                "embedded": embedded,
                "lsh_buckets": db.query(MemoryEmbeddingBucket).count(),
                "index_ms": round(index_ms, 2),
                "database_mb": round(db_path.stat().st_size / 1024 / 1024, 2),
                "recall_at_5": round(sum(item["hit"] for item in cases) / len(cases), 2),
                "average_search_ms": round(sum(item["latency_ms"] for item in cases) / len(cases), 2),
                "cases": cases,
            }, ensure_ascii=False, indent=2))
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    main()
