"""情侣共同记忆：多源同步、结构化提取与混合检索。"""
import base64
import hashlib
import json
import re
import threading
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import date, datetime, time, timedelta
from typing import Dict, List

import numpy as np
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import (
    Anniversary,
    CoupleAISettings,
    Diary,
    Message,
    MemoryCandidate,
    MemoryEmbeddingBucket,
    MemoryEventHistory,
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
    CHAT_BATCH_SIZE = 30
    CHAT_BATCH_OVERLAP = 8
    LSH_TABLES = 4
    LSH_BITS = 12
    EXACT_VECTOR_LIMIT = 3000
    MIN_RELEVANCE = 0.48
    LOCAL_MIN_RELEVANCE = 0.06
    MIN_KEYWORD_SUPPORT = 0.04
    STRONG_SEMANTIC_SUPPORT = 0.72

    def __init__(self):
        self._sync_locks: Dict[int, threading.Lock] = {}
        self._sync_locks_guard = threading.Lock()
        self._lsh_planes = {}

    def _sync_lock(self, couple_id: int) -> threading.Lock:
        with self._sync_locks_guard:
            return self._sync_locks.setdefault(couple_id, threading.Lock())

    @staticmethod
    def _memory_text(memory: SharedMemory) -> str:
        return " ".join([
            memory.title or "", memory.content or "", memory.location or "", memory.tags or "",
            memory.category or "", memory.event_kind or "", memory.memory_state or "", memory.facts or "",
        ])

    @staticmethod
    def _encode_vector(vector: np.ndarray) -> str:
        return base64.b64encode(np.asarray(vector, dtype=np.float32).tobytes()).decode("ascii")

    @staticmethod
    def _decode_vector(value: str, dimension: int) -> np.ndarray | None:
        try:
            vector = np.frombuffer(base64.b64decode(value), dtype=np.float32)
            return vector if len(vector) == dimension and dimension > 0 else None
        except Exception:
            return None

    def _planes(self, model: str, dimension: int) -> np.ndarray:
        key = (model, dimension)
        if key not in self._lsh_planes:
            seed = int.from_bytes(hashlib.sha256(f"{model}:{dimension}".encode()).digest()[:8], "little")
            rng = np.random.default_rng(seed)
            self._lsh_planes[key] = rng.standard_normal(
                (self.LSH_TABLES, self.LSH_BITS, dimension), dtype=np.float32
            )
        return self._lsh_planes[key]

    def _vector_buckets(self, vector: np.ndarray, model: str) -> List[str]:
        projections = np.einsum("tbd,d->tb", self._planes(model, len(vector)), vector)
        buckets = []
        for row in projections:
            value = sum((1 << index) for index, positive in enumerate(row >= 0) if positive)
            buckets.append(str(value))
        return buckets

    def ensure_embeddings(self, db: Session, couple_id: int, limit: int = 128) -> Dict:
        """增量补齐或重建持久化语义向量与 LSH 桶。"""
        model = ai_service.embedding_index_model
        rows = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.status == "confirmed",
            SharedMemory.is_active.is_(True),
            or_(SharedMemory.embedding_b64 == "", SharedMemory.embedding_b64.is_(None), SharedMemory.embedding_model != model),
        ).order_by(SharedMemory.id.asc()).limit(limit).all()
        if not rows:
            return {"embedded": 0, "remaining_embeddings": 0, "embedding_model": model}
        vectors = ai_service.embed_texts([self._memory_text(row) for row in rows])
        if len(vectors) != len(rows):
            raise RuntimeError("embedding service returned an unexpected vector count")
        for memory, vector in zip(rows, vectors):
            db.query(MemoryEmbeddingBucket).filter(MemoryEmbeddingBucket.memory_id == memory.id).delete(
                synchronize_session=False
            )
            memory.embedding_b64 = self._encode_vector(vector)
            memory.embedding_model = model
            memory.embedding_dim = len(vector)
            memory.embedding_updated_at = datetime.utcnow()
            for table_index, bucket in enumerate(self._vector_buckets(vector, model)):
                db.add(MemoryEmbeddingBucket(
                    memory_id=memory.id,
                    couple_id=couple_id,
                    model=model,
                    table_index=table_index,
                    bucket=bucket,
                ))
        db.commit()
        remaining = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.status == "confirmed",
            SharedMemory.is_active.is_(True),
            or_(SharedMemory.embedding_b64 == "", SharedMemory.embedding_b64.is_(None), SharedMemory.embedding_model != model),
        ).count()
        return {"embedded": len(rows), "remaining_embeddings": remaining, "embedding_model": model}

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
        previous_search_text = self._memory_text(memory) if not created else ""
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
        if created or self._memory_text(memory) != previous_search_text:
            memory.embedding_b64 = ""
            memory.embedding_model = ""
            memory.embedding_dim = 0
            memory.embedding_updated_at = None
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

        chat_result = {"processed_messages": 0, "created_events": 0, "merged_events": 0, "remaining_messages": 0}
        if settings.include_chat:
            chat_result = self.sync_chat_events(db, couple_id, max_batches=4)
            created += chat_result["created_events"]
            touched += chat_result["created_events"] + chat_result["merged_events"]

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
        embedding_result = {"embedded": 0, "remaining_embeddings": 0, "embedding_model": ai_service.embedding_index_model}
        try:
            embedding_result = self.ensure_embeddings(db, couple_id, limit=128)
        except Exception as exc:
            db.rollback()
            embedding_result["embedding_error"] = str(exc)[:500]
        return {
            "enabled": True,
            "created": created,
            "updated": max(0, touched - created),
            "total": total,
            **chat_result,
            "last_synced_message_id": settings.last_synced_message_id or 0,
            **embedding_result,
        }

    @staticmethod
    def _parse_datetime(value: str | None, fallback: datetime | None = None) -> datetime | None:
        if not value:
            return fallback
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _json_ids(value: str | None) -> List[int]:
        try:
            return [int(item) for item in json.loads(value or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _find_merge_target(self, db: Session, couple_id: int, event: Dict, event_at: datetime | None):
        query = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.source_type == "chat_event",
            SharedMemory.category == event["category"],
            SharedMemory.is_active.is_(True),
        )
        if event_at:
            query = query.filter(or_(
                SharedMemory.event_date.is_(None),
                SharedMemory.event_date.between(event_at - timedelta(days=45), event_at + timedelta(days=45)),
            ))
        candidates = query.order_by(SharedMemory.updated_at.desc()).limit(120).all()
        incoming = f"{event['title']} {event['summary']} {event.get('location', '')}".lower()
        incoming_terms = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9]+", incoming))
        best = None
        best_score = 0.0
        best_text_score = 0.0
        best_entity_score = 0.0
        for memory in candidates:
            existing = f"{memory.title} {memory.content} {memory.location or ''}".lower()
            existing_terms = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9]+", existing))
            overlap = len(incoming_terms & existing_terms) / max(1, min(len(incoming_terms), len(existing_terms)))
            title_similarity = SequenceMatcher(None, event["title"].lower(), (memory.title or "").lower()).ratio()
            location_match = bool(event.get("location") and event.get("location") == memory.location)
            score = max(overlap, title_similarity) + (0.15 if location_match else 0.0)
            if score > best_score:
                best, best_score = memory, score
        return best if best_score >= 0.58 else None

    def _store_chat_event(self, db: Session, couple_id: int, event: Dict, batch_messages: List[Message]) -> bool:
        message_map = {item.id: item for item in batch_messages}
        source_ids = [item for item in event.get("source_message_ids", []) if item in message_map]
        if not source_ids:
            return False
        fallback_date = min(message_map[item].created_at for item in source_ids)
        event_at = self._parse_datetime(event.get("event_date"), fallback_date)
        event_end = self._parse_datetime(event.get("event_end"))
        target = self._find_merge_target(db, couple_id, event, event_at)
        status = "confirmed" if event.get("confidence", 0.0) >= 0.6 else "uncertain"
        if target:
            combined_ids = sorted(set(self._json_ids(target.source_message_ids)) | set(source_ids))
            # 新批次代表事件的后续发展，保留最新整理结果并持续附加证据。
            target.title = event["title"][:200]
            target.content = event["summary"][:8000]
            target.location = event.get("location", "")[:100] or target.location
            target.emotion = event.get("emotion", "")[:30] or target.emotion
            target.tags = json.dumps(event.get("tags", []), ensure_ascii=False)
            target.importance = max(target.importance or 0.0, event.get("importance", 0.5))
            target.confidence = max(target.confidence or 0.0, event.get("confidence", 0.5))
            target.status = "confirmed" if target.confidence >= 0.6 else status
            target.memory_state = event.get("state", "uncertain")
            target.event_date = min(filter(None, [target.event_date, event_at]), default=event_at)
            target.event_end = event_end or max(message_map[item].created_at for item in source_ids)
            target.source_message_ids = json.dumps(combined_ids)
            target.embedding_b64 = ""
            target.embedding_model = ""
            target.embedding_dim = 0
            target.embedding_updated_at = None
            target.updated_at = datetime.utcnow()
            return False

        first_id, last_id = min(source_ids), max(source_ids)
        # 同一组证据可能同时支持多个不同事件（例如“加入共同提醒”既是事实，
        # 也可能被模型整理为计划）。只用消息范围会让这些事件争用同一个唯一键。
        # 内容指纹既避免碰撞，也让同一模型结果在失败重试时保持幂等。
        fingerprint_text = "\n".join([
            event.get("category", "event"),
            event.get("state", "uncertain"),
            event.get("title", ""),
            event.get("summary", ""),
        ])
        fingerprint = hashlib.sha256(fingerprint_text.encode("utf-8")).hexdigest()[:12]
        memory = SharedMemory(
            couple_id=couple_id,
            source_type="chat_event",
            source_id=f"messages-{first_id}-{last_id}-{fingerprint}",
            title=event["title"][:200],
            content=event["summary"][:8000],
            event_date=event_at,
            event_end=event_end or max(message_map[item].created_at for item in source_ids),
            location=event.get("location", "")[:100],
            emotion=event.get("emotion", "")[:30],
            tags=json.dumps(event.get("tags", []), ensure_ascii=False),
            importance=event.get("importance", 0.5),
            confidence=event.get("confidence", 0.5),
            status=status,
            visibility="shared",
            category=event.get("category", "event"),
            memory_state=event.get("state", "uncertain"),
            source_message_ids=json.dumps(sorted(source_ids)),
            is_active=True,
        )
        db.add(memory)
        return True

    @staticmethod
    def _json_list(value: str | None) -> List:
        try:
            parsed = json.loads(value or "[]")
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _resolve_event_date(
        self, event: Dict, message_map: Dict[int, Message], source_ids: List[int]
    ) -> datetime | None:
        """消息时间是可信锚点；模型时间只有与证据一致时才可覆盖它。"""
        source_dates = [message_map[item].created_at for item in source_ids if item in message_map]
        if not source_dates:
            return None
        kind = str(event.get("event_kind") or event.get("category") or "event").lower()
        anchor = max(source_dates) if kind in {"preference", "conflict", "reconciliation"} else min(source_dates)
        parsed = self._parse_datetime(event.get("event_date"))
        if parsed is None:
            return anchor
        evidence = " ".join(message_map[item].content or "" for item in source_ids if item in message_map)
        has_absolute_date = bool(re.search(r"(?:19|20)\d{2}\s*(?:年|[-/.])\s*\d{1,2}", evidence))
        if has_absolute_date or abs((parsed - anchor).total_seconds()) <= 7 * 86400:
            return parsed
        return anchor

    def _normalize_event_facts(
        self, event: Dict, message_map: Dict[int, Message], source_ids: List[int]
    ) -> List[Dict]:
        facts = []
        raw_facts = event.get("facts") or [{
            "type": event.get("event_kind") or event.get("category") or "fact",
            "value": event.get("summary") or event.get("title") or "",
            "occurred_at": event.get("event_date") or "",
            "source_message_ids": source_ids,
        }]
        for raw in raw_facts:
            if not isinstance(raw, dict):
                continue
            value = re.sub(r"\s+", " ", str(raw.get("value") or "")).strip()[:500]
            if not value:
                continue
            fact_ids = []
            for item in raw.get("source_message_ids") or source_ids:
                try:
                    item = int(item)
                except (TypeError, ValueError):
                    continue
                if item in source_ids and item in message_map and item not in fact_ids:
                    fact_ids.append(item)
            if not fact_ids:
                fact_ids = list(source_ids)
            occurred = self._parse_datetime(raw.get("occurred_at"))
            if occurred is None:
                occurred = min(message_map[item].created_at for item in fact_ids)
            facts.append({
                "type": str(raw.get("type") or "fact")[:40],
                "value": value,
                "occurred_at": occurred.isoformat(),
                "source_message_ids": fact_ids,
            })
        return facts

    @staticmethod
    def _merge_facts(existing: List[Dict], incoming: List[Dict]) -> List[Dict]:
        current_types = {"current_preference", "preference_current", "current_value"}
        incoming_current_values = {
            re.sub(r"\s+", "", str(fact.get("value") or "")).lower()
            for fact in incoming if str(fact.get("type") or "").lower() in current_types
        }
        merged = []
        seen = set()
        for fact in [*existing, *incoming]:
            fact = dict(fact)
            value = re.sub(r"\s+", "", str(fact.get("value") or "")).lower()
            if (
                fact in existing
                and str(fact.get("type") or "").lower() in current_types
                and incoming_current_values
                and value not in incoming_current_values
            ):
                fact["type"] = "previous_preference"
            key = (str(fact.get("type") or "fact").lower(), value)
            if not value or key in seen:
                continue
            seen.add(key)
            merged.append(fact)
        return merged[-80:]

    @staticmethod
    def _candidate_key(event: Dict, event_at: datetime | None) -> str:
        kind = str(event.get("event_kind") or event.get("category") or "event").lower()
        hint = str(event.get("event_key") or event.get("title") or "").lower()
        hint = re.sub(r"(?:planned|ongoing|completed|cancelled|uncertain|计划中|已完成|已取消)", "", hint)
        hint = re.sub(r"[^a-z0-9\u4e00-\u9fa5:]+", "", hint)[:100]
        if hint.startswith(f"{kind}:"):
            hint = hint[len(kind) + 1:]
        # 一次性活动用日期防止同城多次经历误合并；计划和偏好跨日期沿用同一主题。
        date_part = "" if kind in {"plan", "preference"} else f":{event_at:%Y-%m-%d}" if event_at else ""
        return f"{kind}:{hint or 'unknown'}{date_part}"[:160]

    def _find_candidate(self, db: Session, couple_id: int, event: Dict, event_at: datetime | None):
        key = self._candidate_key(event, event_at)
        exact = db.query(MemoryCandidate).filter(
            MemoryCandidate.couple_id == couple_id,
            MemoryCandidate.event_key == key,
        ).order_by(MemoryCandidate.updated_at.desc()).first()
        if exact:
            return exact, key
        kind = str(event.get("event_kind") or event.get("category") or "event").lower()
        query = db.query(MemoryCandidate).filter(
            MemoryCandidate.couple_id == couple_id,
            MemoryCandidate.event_kind == kind,
        )
        if event_at and kind not in {"plan", "preference"}:
            query = query.filter(MemoryCandidate.event_date.between(
                event_at - timedelta(days=2), event_at + timedelta(days=2)
            ))
        candidates = query.order_by(MemoryCandidate.updated_at.desc()).limit(40).all()
        incoming_entities = set(str(item).lower() for item in event.get("entities", []) if str(item).strip())
        incoming_hint = str(event.get("event_key") or event.get("title") or "").lower()
        generic_entities = {"用户", "用户1", "用户2", "双方", "情侣", "偏好", "计划", "事件"}
        incoming_entities -= generic_entities
        incoming_topic = re.sub(r"^[a-z_]+:", "", incoming_hint)
        best = None
        best_score = 0.0
        for candidate in candidates:
            existing_entities = set(str(item).lower() for item in self._json_list(candidate.entities)) - generic_entities
            entity_score = len(incoming_entities & existing_entities) / max(1, min(len(incoming_entities), len(existing_entities)))
            existing_topic = re.sub(r"^[a-z_]+:", "", (candidate.title_hint or "").lower())
            text_score = SequenceMatcher(None, incoming_topic, existing_topic).ratio()
            score = max(entity_score, text_score)
            if score > best_score:
                best, best_score = candidate, score
                best_text_score, best_entity_score = text_score, entity_score
        # 模糊合并必须有强主题或实体证据，避免同城多次旅行、相似计划被错误合并。
        if kind in {"preference", "plan"}:
            strong_match = best is not None and best_text_score >= 0.82 and (
                not incoming_entities or best_entity_score >= 0.5
            )
        else:
            strong_match = best is not None and best_score >= 0.68
        return (best, best.event_key) if strong_match else (None, key)

    @staticmethod
    def _candidate_boundary(event_kind: str, source_text: str, suggested_state: str):
        """业务状态边界与聚合窗口边界分开；静默不会自动变成完成。"""
        if any(marker in source_text for marker in ("取消", "不去了", "不去啦", "暂时不去")):
            return "cancelled", "closed", "explicit_cancellation"
        if event_kind == "conflict":
            resolved = any(marker in source_text for marker in ("和好", "道歉", "说清楚", "说开了"))
            resolution = any(marker in source_text for marker in ("办法", "约定", "以后", "解决", "共识"))
            return ("completed", "closed", "explicit_resolution") if resolved and resolution else (
                "ongoing", "open", ""
            )
        if event_kind == "reconciliation":
            resolved = any(marker in source_text for marker in ("和好", "道歉", "说清楚", "说开了"))
            return ("completed", "closed", "explicit_resolution") if resolved else (
                "uncertain", "open", ""
            )
        if event_kind in {"trip", "date", "activity"}:
            ended = any(marker in source_text for marker in ("旅行结束", "活动结束", "约会结束", "回到家", "回家了", "返程", "回来了"))
            happened = suggested_state == "completed" or any(
                marker in source_text for marker in ("去了", "到达", "抵达", "吃了", "看了", "参加了", "完成了")
            )
            return ("completed", "closed", "explicit_completion") if ended or happened else (
                "ongoing" if suggested_state != "planned" else "planned", "open", ""
            )
        if event_kind == "preference":
            return "ongoing", "open", ""
        if event_kind == "plan":
            if any(marker in source_text for marker in ("完成了", "已经去了", "已经参加", "顺利结束")):
                return "completed", "closed", "explicit_completion"
            return "planned", "open", ""
        if event_kind in {"gift", "fact"}:
            return suggested_state if suggested_state in {"completed", "ongoing"} else "completed", "closed", "explicit_fact"
        return suggested_state or "uncertain", "open", ""

    def _merge_candidate_fragment(
        self, db: Session, couple_id: int, event: Dict, batch_messages: List[Message]
    ):
        message_map = {item.id: item for item in batch_messages}
        source_ids = sorted({int(item) for item in event.get("source_message_ids", []) if int(item) in message_map})
        if not source_ids:
            return None, False
        event_at = self._resolve_event_date(event, message_map, source_ids)
        candidate, event_key = self._find_candidate(db, couple_id, event, event_at)
        created = candidate is None
        if candidate is None:
            candidate = MemoryCandidate(
                couple_id=couple_id, event_key=event_key,
                event_kind=event.get("event_kind") or event.get("category") or "event",
                category=event.get("category") or "event", event_date=event_at,
                first_seen_at=min(message_map[item].created_at for item in source_ids),
            )
            db.add(candidate)
        old_ids = set(self._json_ids(candidate.source_message_ids))
        changed = bool(set(source_ids) - old_ids) or created
        fragments = self._json_list(candidate.fragments)
        fragment_signature = (event.get("title", ""), tuple(source_ids))
        if not any((item.get("title", ""), tuple(item.get("source_message_ids", []))) == fragment_signature for item in fragments):
            fragments.append({
                "title": event.get("title", ""), "summary": event.get("summary", ""),
                "state": event.get("state", "uncertain"), "location": event.get("location", ""),
                "entities": event.get("entities", []), "source_message_ids": source_ids,
            })
        entities = list(dict.fromkeys(self._json_list(candidate.entities) + list(event.get("entities", []))))
        facts = self._merge_facts(
            self._json_list(candidate.facts), self._normalize_event_facts(event, message_map, source_ids)
        )
        combined_ids = sorted(old_ids | set(source_ids))
        candidate.title_hint = event.get("event_key") or event.get("title") or candidate.title_hint
        candidate.fragments = json.dumps(fragments[-40:], ensure_ascii=False)
        candidate.facts = json.dumps(facts, ensure_ascii=False)
        candidate.entities = json.dumps(entities[:30], ensure_ascii=False)
        candidate.source_message_ids = json.dumps(combined_ids)
        dates = [value for value in (candidate.event_date, event_at) if value is not None]
        candidate.event_date = max(dates) if candidate.event_kind == "preference" else min(dates)
        evidence_dates = [row[0] for row in db.query(Message.created_at).filter(Message.id.in_(combined_ids)).all()]
        candidate.event_end = max(evidence_dates) if evidence_dates else event_at
        candidate.confidence = max(candidate.confidence or 0.0, event.get("confidence", 0.5))
        candidate.last_seen_at = max(message_map[item].created_at for item in source_ids)
        candidate.quiet_until = candidate.last_seen_at + timedelta(hours=48)
        source_text = " ".join(
            item.content or "" for item in db.query(Message).filter(Message.id.in_(combined_ids)).order_by(Message.id).all()
        )
        state, lifecycle, reason = self._candidate_boundary(
            candidate.event_kind, source_text, event.get("state", "uncertain")
        )
        candidate.state, candidate.lifecycle, candidate.closure_reason = state, lifecycle, reason
        candidate.updated_at = datetime.utcnow()
        db.flush()
        return candidate, changed

    def _materialize_candidate(self, db: Session, candidate: MemoryCandidate) -> bool:
        source_ids = self._json_ids(candidate.source_message_ids)
        messages = db.query(Message).filter(
            Message.couple_id == candidate.couple_id, Message.id.in_(source_ids)
        ).order_by(Message.id.asc()).all()
        if not messages:
            return False
        candidate_payload = {
            "event_key": candidate.event_key, "event_kind": candidate.event_kind,
            "category": candidate.category, "state": candidate.state,
            "lifecycle": candidate.lifecycle, "closure_reason": candidate.closure_reason,
            "title_hint": candidate.title_hint, "entities": self._json_list(candidate.entities),
            "fragments": self._json_list(candidate.fragments),
            "facts": self._json_list(candidate.facts),
        }
        summary = ai_service.summarize_memory_candidate(candidate_payload, [{
            "id": item.id, "content": item.content, "created_at": item.created_at.isoformat()
        } for item in messages])
        memory = db.query(SharedMemory).filter(SharedMemory.id == candidate.memory_id).first() if candidate.memory_id else None
        created = memory is None
        if memory is None:
            memory = SharedMemory(
                couple_id=candidate.couple_id, source_type="chat_event",
                source_id=f"candidate-{candidate.id}", content="",
            )
            db.add(memory)
            db.flush()
            candidate.memory_id = memory.id
        previous = (memory.content, memory.memory_state, memory.lifecycle, memory.source_message_ids)
        facts = self._json_list(candidate.facts)
        content = summary["summary"]
        for fact in facts:
            value = str(fact.get("value") or "").strip()
            if value and value not in content:
                content = f"{content}；{value}" if content else value
        memory.title = summary["title"]
        memory.content = content[:8000]
        memory.event_key = candidate.event_key
        memory.event_kind = candidate.event_kind
        memory.facts = json.dumps(facts, ensure_ascii=False)
        memory.event_date = candidate.event_date
        memory.event_end = candidate.event_end
        memory.valid_from = candidate.event_date if candidate.event_kind == "preference" else None
        memory.valid_to = None
        memory.location = summary.get("location", "")
        memory.emotion = summary.get("emotion", "")
        memory.tags = json.dumps(summary.get("tags", []), ensure_ascii=False)
        memory.importance = summary.get("importance", 0.6)
        memory.confidence = candidate.confidence
        memory.state_confidence = candidate.confidence
        memory.status = "confirmed" if candidate.confidence >= 0.6 else "uncertain"
        memory.visibility = "shared"
        memory.category = candidate.category
        memory.memory_state = candidate.state
        memory.lifecycle = candidate.lifecycle
        memory.closure_reason = candidate.closure_reason
        memory.source_message_ids = candidate.source_message_ids
        memory.is_active = True
        memory.embedding_b64 = ""
        memory.embedding_model = ""
        memory.embedding_dim = 0
        memory.embedding_updated_at = None
        memory.updated_at = datetime.utcnow()
        current = (memory.content, memory.memory_state, memory.lifecycle, memory.source_message_ids)
        if created or current != previous:
            db.add(MemoryEventHistory(
                memory_id=memory.id, candidate_id=candidate.id, state=memory.memory_state,
                lifecycle=memory.lifecycle, closure_reason=memory.closure_reason,
                title=memory.title, content=memory.content,
                facts=memory.facts,
                source_message_ids=memory.source_message_ids,
            ))
            memory.version = 1 if created else (memory.version or 1) + 1
        return created

    def sync_chat_events(self, db: Session, couple_id: int, max_batches: int = 4) -> Dict:
        """从持久化游标向后整理聊天；原文不复制到记忆表。"""
        lock = self._sync_lock(couple_id)
        if not lock.acquire(blocking=False):
            return {"processed_messages": 0, "created_events": 0, "merged_events": 0, "remaining_messages": 0}
        try:
            settings = self.get_settings(db, couple_id)
            processed = created = merged = 0
            for _ in range(max_batches):
                cursor = settings.last_synced_message_id or 0
                batch = db.query(Message).filter(
                    Message.couple_id == couple_id,
                    Message.id > cursor,
                ).order_by(Message.id.asc()).limit(self.CHAT_BATCH_SIZE).all()
                if not batch:
                    break
                overlap = []
                if cursor:
                    overlap = db.query(Message).filter(
                        Message.couple_id == couple_id,
                        Message.id <= cursor,
                        Message.msg_type == "text",
                    ).order_by(Message.id.desc()).limit(self.CHAT_BATCH_OVERLAP).all()
                    overlap.reverse()
                text_messages = overlap + [
                    item for item in batch if item.msg_type == "text" and (item.content or "").strip()
                ]
                payload = [{
                    "id": item.id,
                    "sender_id": item.sender_id,
                    "content": item.content,
                    "created_at": item.created_at.isoformat(),
                } for item in text_messages]
                try:
                    events = ai_service.extract_memory_events(payload)
                    touched_candidates = {}
                    for event in events:
                        candidate, changed = self._merge_candidate_fragment(db, couple_id, event, text_messages)
                        if candidate is not None and changed:
                            touched_candidates[candidate.id] = candidate
                    for candidate in touched_candidates.values():
                        if self._materialize_candidate(db, candidate):
                            created += 1
                        else:
                            merged += 1
                    settings.last_synced_message_id = batch[-1].id
                    settings.sync_error = ""
                    settings.sync_updated_at = datetime.utcnow()
                    db.commit()
                    processed += len(batch)
                except Exception as exc:
                    db.rollback()
                    settings = self.get_settings(db, couple_id)
                    settings.sync_error = str(exc)[:1000]
                    settings.sync_updated_at = datetime.utcnow()
                    db.commit()
                    break
            remaining = db.query(Message).filter(
                Message.couple_id == couple_id,
                Message.id > (settings.last_synced_message_id or 0),
            ).count()
            return {
                "processed_messages": processed,
                "created_events": created,
                "merged_events": merged,
                "remaining_messages": remaining,
            }
        finally:
            lock.release()

    def extract_candidates(self, db: Session, couple_id: int, limit: int = 8) -> List[SharedMemory]:
        # 保留旧 API 兼容性；事件已在游标同步阶段自动整理并按置信度入库。
        self.sync_chat_events(db, couple_id, max_batches=max(1, limit // 2))
        return []

    @staticmethod
    def _query_terms(query: str) -> List[str]:
        terms = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
        for sequence in re.findall(r"[\u4e00-\u9fa5]+", query):
            if len(sequence) <= 3:
                terms.add(sequence)
            else:
                for size in (2, 3):
                    terms.update(sequence[index:index + size] for index in range(len(sequence) - size + 1))
        return sorted(terms, key=len, reverse=True)[:32]

    def _lsh_candidate_ids(self, db: Session, couple_id: int, model: str, vector: np.ndarray) -> List[int]:
        conditions = []
        for table_index, bucket_text in enumerate(self._vector_buckets(vector, model)):
            bucket = int(bucket_text)
            nearby = [str(bucket)] + [str(bucket ^ (1 << bit)) for bit in range(self.LSH_BITS)]
            conditions.append(and_(
                MemoryEmbeddingBucket.table_index == table_index,
                MemoryEmbeddingBucket.bucket.in_(nearby),
            ))
        rows = db.query(MemoryEmbeddingBucket.memory_id).filter(
            MemoryEmbeddingBucket.couple_id == couple_id,
            MemoryEmbeddingBucket.model == model,
            or_(*conditions),
        ).all()
        counts = defaultdict(int)
        for (memory_id,) in rows:
            counts[memory_id] += 1
        return [memory_id for memory_id, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:1500]]

    def search(
        self,
        db: Session,
        couple_id: int,
        query: str,
        top_k: int = 5,
        user_id: int | None = None,
    ) -> List[Dict]:
        base = db.query(SharedMemory).filter(
            SharedMemory.couple_id == couple_id,
            SharedMemory.status == "confirmed",
            SharedMemory.is_active.is_(True),
        )
        if user_id is not None:
            base = base.filter(or_(
                SharedMemory.visibility == "shared",
                SharedMemory.visibility.is_(None),
                SharedMemory.owner_id == user_id,
            ))
        try:
            self.ensure_embeddings(db, couple_id, limit=256)
            model = ai_service.embedding_index_model
            query_vector = ai_service.embed_texts([query])[0]
        except Exception:
            db.rollback()
            model = ""
            query_vector = None

        query_terms = self._query_terms(query)
        existence_question = any(marker in query for marker in ("有没有", "是否", "是不是", "曾经", "曾在", "吗"))
        generic_query_text = (
            "我们你们两个人对方有没有是否是不是曾经曾在一起去过参加体验安排回忆细节"
            "哪一年什么时候现在以前后来最后最喜欢一直明确说过约定决定共同计划取消完成"
            "生日纪念日礼物问题事情关于"
        )
        distinctive_terms = [term for term in query_terms if term not in generic_query_text]
        total = base.count()
        if query_vector is not None and total <= self.EXACT_VECTOR_LIMIT:
            memories = base.all()
        else:
            candidate_ids = self._lsh_candidate_ids(db, couple_id, model, query_vector) if query_vector is not None else []
            lexical_conditions = []
            for term in query_terms:
                pattern = f"%{term}%"
                lexical_conditions.extend([
                    SharedMemory.title.ilike(pattern),
                    SharedMemory.content.ilike(pattern),
                    SharedMemory.location.ilike(pattern),
                    SharedMemory.tags.ilike(pattern),
                ])
            if lexical_conditions:
                lexical_ids = [row[0] for row in base.with_entities(SharedMemory.id).filter(
                    or_(*lexical_conditions)
                ).limit(800).all()]
                candidate_ids = list(dict.fromkeys(candidate_ids + lexical_ids))
            memories = base.filter(SharedMemory.id.in_(candidate_ids)).all() if candidate_ids else []
        if not memories:
            return []
        corpus = [" ".join([
            m.title or "", m.content or "", m.location or "", m.tags or "", m.facts or "",
            m.event_kind or "", m.memory_state or "",
        ]) for m in memories]
        scores = []
        now = datetime.utcnow()
        min_relevance = self.LOCAL_MIN_RELEVANCE if model == "local-hash-v1" else self.MIN_RELEVANCE
        year_match = re.search(r"(?<!\d)(20\d{2})\s*年?", query)
        month_match = re.search(r"(?:20\d{2}\s*年\s*)?(1[0-2]|0?[1-9])\s*月", query)
        query_year = int(year_match.group(1)) if year_match else None
        query_month = int(month_match.group(1)) if month_match else None
        wants_current_preference = "现在" in query and any(
            marker in query for marker in ("喜欢", "偏好", "口味", "选择", "饮品", "运动", "座位")
        )
        wants_cancelled = any(marker in query for marker in ("取消", "不去了", "没去成"))
        for index, memory in enumerate(memories):
            text = corpus[index].lower()
            keyword = sum(1 for term in query_terms if term in text) / max(1, len(query_terms))
            distinctive_matches = [term for term in distinctive_terms if term in text]
            stored_vector = self._decode_vector(memory.embedding_b64 or "", memory.embedding_dim or 0)
            semantic = (
                float(np.dot(query_vector, stored_vector))
                if query_vector is not None and stored_vector is not None and memory.embedding_model == model
                else 0.0
            )
            memory_date = memory.event_date or memory.created_at
            # 问题明确给出年月时，把它当作事实约束，而不是弱排序信号。
            if query_year and memory_date and memory_date.year != query_year:
                continue
            if query_month and memory_date and memory_date.month != query_month:
                continue
            if wants_current_preference and memory.category != "preference":
                continue
            if wants_cancelled and memory.memory_state != "cancelled":
                continue
            age_days = (now - (memory.event_date or memory.created_at)).days
            recency = max(0.0, 1.0 - max(age_days, 0) / 3650) * 0.05
            relevance = max(0.0, semantic) * 0.75 + keyword * 0.25
            # 低相关语义分在大库中普遍存在；必须有词面证据或很强的语义证据才可进入答案上下文。
            supported = keyword >= self.MIN_KEYWORD_SUPPORT or semantic >= self.STRONG_SEMANTIC_SUPPORT
            if existence_question and not (
                any(len(term) >= 3 for term in distinctive_matches) or len(distinctive_matches) >= 2
            ):
                continue
            if relevance >= min_relevance and supported:
                metadata_boost = 0.0
                if wants_current_preference and memory.memory_state == "ongoing" and memory.valid_to is None:
                    metadata_boost += 0.12
                if wants_cancelled and memory.memory_state == "cancelled":
                    metadata_boost += 0.12
                score = relevance + recency + memory.importance * 0.03 + metadata_boost
                scores.append((score, memory))
        ranked = sorted(scores, key=lambda item: item[0], reverse=True)[:top_k]
        results = []
        for score, memory in ranked:
            data = self.serialize(memory, score)
            source_ids = self._json_ids(memory.source_message_ids)
            if source_ids:
                evidence = db.query(Message).filter(
                    Message.couple_id == couple_id,
                    Message.id.in_(source_ids[:12]),
                ).order_by(Message.id.asc()).all()
                data["evidence"] = [
                    {"message_id": item.id, "created_at": item.created_at.isoformat(), "content": item.content}
                    for item in evidence
                ]
            results.append(data)
        return results

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
            "event_key": memory.event_key or "",
            "event_kind": memory.event_kind or memory.category or "event",
            "facts": self._json_list(memory.facts),
            "memory_state": memory.memory_state or "completed",
            "lifecycle": memory.lifecycle or "closed",
            "closure_reason": memory.closure_reason or "",
            "state_confidence": memory.state_confidence if memory.state_confidence is not None else 1.0,
            "confidence": memory.confidence if memory.confidence is not None else 1.0,
            "event_end": memory.event_end.isoformat() if memory.event_end else None,
            "valid_from": memory.valid_from.isoformat() if memory.valid_from else None,
            "valid_to": memory.valid_to.isoformat() if memory.valid_to else None,
            "source_message_ids": self._json_ids(memory.source_message_ids),
            "version": memory.version or 1,
            "is_active": memory.is_active if memory.is_active is not None else True,
            "created_at": memory.created_at.isoformat(),
        }
        if score is not None:
            data["score"] = round(score, 4)
        return data


memory_service = MemoryService()
