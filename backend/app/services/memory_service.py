"""情侣共同记忆：多源同步、结构化提取与混合检索。"""
import json
import re
from datetime import date, datetime, time, timedelta
from typing import Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import (
    Anniversary,
    CoupleAISettings,
    Diary,
    Message,
    Photo,
    SharedMemory,
)
from .ai_service import ai_service


DEFAULT_QUESTIONS = [
    "今天有什么小事让你想起了对方？",
    "最近对方做过哪件事让你觉得很温暖？",
    "如果周末只有半天时间，你最想和对方做什么？",
    "你最想和对方重温哪一次共同经历？",
    "最近有什么压力，希望对方怎样陪伴你？",
    "你觉得两个人最近最值得庆祝的事情是什么？",
    "下一次旅行，你最想一起去哪里？为什么？",
    "对方身上哪一个小习惯最让你觉得可爱？",
    "今天想认真对对方说的一句话是什么？",
    "今年你最期待两个人共同完成什么目标？",
]


class MemoryService:
    def get_settings(self, db: Session, couple_id: int) -> CoupleAISettings:
        settings = db.query(CoupleAISettings).filter(CoupleAISettings.couple_id == couple_id).first()
        if not settings:
            settings = CoupleAISettings(couple_id=couple_id, enabled=False)
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings

    def _upsert(
        self,
        db: Session,
        couple_id: int,
        source_type: str,
        source_id: str,
        title: str,
        content: str,
        event_date: datetime | None,
        created_by: int | None = None,
        emotion: str = "",
        tags: List[str] | None = None,
        importance: float = 0.5,
        status: str = "confirmed",
        owner_id: int | None = None,
        visibility: str = "shared",
        category: str = "event",
    ) -> bool:
        if not content.strip():
            return False
        memory = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.source_type == source_type,
            SharedMemory.source_id == str(source_id),
        ).first()
        created = memory is None
        if not memory:
            memory = SharedMemory(
                couple_id=couple_id,
                source_type=source_type,
                source_id=str(source_id),
            )
            db.add(memory)
        memory.title = title[:200]
        memory.content = content[:8000]
        memory.event_date = event_date
        memory.created_by = created_by
        memory.owner_id = owner_id
        memory.visibility = visibility
        memory.category = category
        memory.is_active = True
        memory.emotion = emotion[:30]
        memory.tags = json.dumps(tags or [], ensure_ascii=False)
        memory.importance = importance
        memory.status = status
        return created

    def create_manual(
        self,
        db: Session,
        couple_id: int,
        user_id: int,
        title: str,
        content: str,
        visibility: str,
        category: str,
        event_date: datetime | None = None,
        location: str = "",
        emotion: str = "",
    ) -> SharedMemory:
        """写入事实/偏好；同一用户同标题偏好自动形成新版本。"""
        if visibility not in {"shared", "private"}:
            raise ValueError("visibility must be shared or private")
        if category not in {"event", "preference", "plan"}:
            raise ValueError("unsupported category")
        version = 1
        if category == "preference":
            previous = db.query(SharedMemory).filter(
                SharedMemory.couple_id == couple_id,
                SharedMemory.owner_id == user_id,
                SharedMemory.category == "preference",
                SharedMemory.title == title.strip(),
                SharedMemory.is_active.is_(True),
            ).order_by(SharedMemory.version.desc()).first()
            if previous:
                previous.is_active = False
                version = (previous.version or 1) + 1
        memory = SharedMemory(
            couple_id=couple_id,
            source_type="manual",
            source_id=f"user-{user_id}-{datetime.utcnow().timestamp()}",
            title=title.strip()[:200],
            content=content.strip()[:8000],
            event_date=event_date or datetime.utcnow(),
            location=location.strip()[:100],
            emotion=emotion.strip()[:30],
            tags=json.dumps(["手动记录", category], ensure_ascii=False),
            importance=0.75 if category == "preference" else 0.6,
            status="confirmed",
            created_by=user_id,
            owner_id=user_id,
            visibility=visibility,
            category=category,
            version=version,
            is_active=True,
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        return memory

    def sync_sources(self, db: Session, couple_id: int) -> Dict:
        settings = self.get_settings(db, couple_id)
        if not settings.enabled:
            return {"enabled": False, "created": 0, "updated": 0, "total": 0}

        created = 0
        touched = 0
        if settings.include_diary:
            for item in db.query(Diary).filter(Diary.couple_id == couple_id).all():
                created += int(self._upsert(
                    db, couple_id, "diary", str(item.id), item.title or "共同日记",
                    item.content, item.created_at, item.author_id, item.mood,
                    ["日记"] + ([item.mood] if item.mood else []), 0.7,
                ))
                touched += 1

        if settings.include_chat:
            messages = db.query(Message).filter(
                Message.couple_id == couple_id,
                Message.msg_type == "text",
            ).order_by(Message.created_at.desc()).limit(500).all()
            for item in messages:
                if len((item.content or "").strip()) < 4:
                    continue
                created += int(self._upsert(
                    db, couple_id, "chat", str(item.id), "聊天片段",
                    item.content, item.created_at, item.sender_id, tags=["聊天"], importance=0.35,
                ))
                touched += 1

        if settings.include_anniversary:
            for item in db.query(Anniversary).filter(Anniversary.couple_id == couple_id).all():
                event_at = datetime.combine(item.date, time.min)
                created += int(self._upsert(
                    db, couple_id, "anniversary", str(item.id), item.title,
                    item.description or f"纪念日：{item.title}", event_at,
                    tags=["纪念日"], importance=0.95,
                ))
                touched += 1

        if settings.include_album:
            for item in db.query(Photo).filter(Photo.couple_id == couple_id).all():
                created += int(self._upsert(
                    db, couple_id, "photo", str(item.id), item.filename,
                    f"共同相册照片：{item.filename}", item.created_at, item.uploader_id,
                    tags=["相册", "照片"], importance=0.55,
                ))
                touched += 1

        db.commit()
        total = db.query(SharedMemory).filter(SharedMemory.couple_id == couple_id).count()
        return {"enabled": True, "created": created, "updated": touched - created, "total": total}

    def extract_candidates(self, db: Session, couple_id: int, limit: int = 8) -> List[SharedMemory]:
        settings = self.get_settings(db, couple_id)
        if not settings.enabled:
            return []
        raw = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.status == "confirmed",
            SharedMemory.source_type.in_(["diary", "chat"]),
        ).order_by(SharedMemory.event_date.desc()).limit(limit).all()
        candidates = []
        for item in raw:
            extracted = ai_service.extract_memory(item.content, item.title)
            source_id = f"{item.source_type}-{item.source_id}"
            exists = db.query(SharedMemory).filter(
                SharedMemory.couple_id == couple_id,
                SharedMemory.source_type == "ai_extract",
                SharedMemory.source_id == source_id,
            ).first()
            if exists:
                continue
            event_at = item.event_date
            raw_date = extracted.get("event_date")
            if raw_date:
                try:
                    event_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass
            self._upsert(
                db, couple_id, "ai_extract", source_id,
                extracted["title"], extracted["summary"], event_at, item.created_by,
                extracted.get("emotion", ""), extracted.get("tags", []),
                extracted.get("importance", 0.5), "pending",
            )
            db.flush()
            candidate = db.query(SharedMemory).filter(
                SharedMemory.couple_id == couple_id,
                SharedMemory.source_type == "ai_extract",
                SharedMemory.source_id == source_id,
            ).first()
            if candidate:
                candidate.location = extracted.get("location", "")
                candidates.append(candidate)
        db.commit()
        return candidates

    def search(
        self,
        db: Session,
        couple_id: int,
        query: str,
        top_k: int = 5,
        user_id: int | None = None,
    ) -> List[Dict]:
        memories = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.status == "confirmed",
            SharedMemory.is_active.is_(True),
        )
        if user_id is not None:
            memories = memories.filter(or_(
                SharedMemory.visibility == "shared",
                SharedMemory.visibility.is_(None),
                SharedMemory.owner_id == user_id,
            ))
        memories = memories.order_by(SharedMemory.event_date.desc()).limit(1500).all()
        if not memories:
            return []
        corpus = [" ".join([m.title or "", m.content or "", m.location or "", m.tags or ""]) for m in memories]
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3), sublinear_tf=True)
        matrix = vectorizer.fit_transform(corpus + [query])
        semantic = cosine_similarity(matrix[-1], matrix[:-1])[0]
        query_terms = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9]+", query.lower()))
        scores = []
        now = datetime.utcnow()
        for index, memory in enumerate(memories):
            text = corpus[index].lower()
            keyword = sum(1 for term in query_terms if term in text) / max(1, len(query_terms))
            age_days = (now - (memory.event_date or memory.created_at)).days
            recency = max(0.0, 1.0 - max(age_days, 0) / 3650) * 0.05
            score = float(semantic[index]) * 0.72 + keyword * 0.23 + recency + memory.importance * 0.03
            scores.append((score, memory))
        ranked = sorted(scores, key=lambda item: item[0], reverse=True)[:top_k]
        return [self.serialize(memory, score) for score, memory in ranked if score > 0.015]

    def serialize(self, memory: SharedMemory, score: float | None = None) -> Dict:
        try:
            tags = json.loads(memory.tags or "[]")
        except json.JSONDecodeError:
            tags = []
        data = {
            "id": memory.id,
            "source_type": memory.source_type,
            "source_id": memory.source_id,
            "title": memory.title,
            "content": memory.content,
            "event_date": memory.event_date.isoformat() if memory.event_date else None,
            "location": memory.location,
            "emotion": memory.emotion,
            "tags": tags,
            "importance": memory.importance,
            "status": memory.status,
            "owner_id": memory.owner_id,
            "visibility": memory.visibility or "shared",
            "category": memory.category or "event",
            "version": memory.version or 1,
            "is_active": memory.is_active if memory.is_active is not None else True,
            "created_at": memory.created_at.isoformat(),
        }
        if score is not None:
            data["score"] = round(score, 4)
        return data


memory_service = MemoryService()
