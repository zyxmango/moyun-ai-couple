"""持久化长期记忆任务队列与独立 Worker 执行逻辑。"""
from __future__ import annotations

import os
import socket
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import (
    CoupleAISettings, MemorySyncJob, MemorySyncRun, Message, SharedMemory,
)
from .ai_service import ai_service
from .memory_service import memory_service


def enqueue_memory_sync(db: Session, couple_id: int) -> MemorySyncJob:
    """幂等入队。同一情侣始终只有一个待处理任务，聊天高峰不会制造任务风暴。"""
    now = datetime.utcnow()
    values = {"couple_id": couple_id, "status": "pending", "requested_at": now, "available_at": now}
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        db.execute(postgresql_insert(MemorySyncJob).values(**values).on_conflict_do_nothing(
            index_elements=[MemorySyncJob.couple_id]
        ))
    elif dialect == "sqlite":
        db.execute(sqlite_insert(MemorySyncJob).values(**values).on_conflict_do_nothing(
            index_elements=[MemorySyncJob.couple_id]
        ))
    else:
        # 当前支持的运行环境是 PostgreSQL/SQLite；保留其他 SQLAlchemy 方言的兼容入口。
        if db.query(MemorySyncJob).filter(MemorySyncJob.couple_id == couple_id).first() is None:
            db.add(MemorySyncJob(**values))
            db.flush()
    job = db.query(MemorySyncJob).filter(MemorySyncJob.couple_id == couple_id).with_for_update().one()
    job.requested_at = now
    if job.status != "running":
        job.status = "pending"
        job.available_at = now
        job.last_error = ""
    db.flush()
    return job


def enqueue_lagging_couples(db: Session) -> int:
    """兜底扫描游标积压；即使 API 入队失败，消息也会最终进入记忆。"""
    rows = db.query(CoupleAISettings).filter(
        CoupleAISettings.enabled.is_(True), CoupleAISettings.include_chat.is_(True)
    ).all()
    queued = 0
    for row in rows:
        newest = db.query(func.max(Message.id)).filter(Message.couple_id == row.couple_id).scalar() or 0
        if newest > (row.last_synced_message_id or 0):
            enqueue_memory_sync(db, row.couple_id)
            queued += 1
    db.commit()
    return queued


def claim_next_job(db: Session, worker_id: str) -> int | None:
    now = datetime.utcnow()
    job = db.query(MemorySyncJob).filter(
        MemorySyncJob.available_at <= now,
        or_(
            MemorySyncJob.status.in_(("pending", "failed")),
            (MemorySyncJob.status == "running") & (MemorySyncJob.lease_until < now),
        ),
    ).order_by(MemorySyncJob.requested_at.asc()).with_for_update(skip_locked=True).first()
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.leased_by = worker_id
    job.lease_until = now + timedelta(seconds=settings.MEMORY_JOB_LEASE_SECONDS)
    job.last_started_at = now
    job.attempts = (job.attempts or 0) + 1
    db.commit()
    return job.couple_id


def _estimated_cost(stats: dict) -> float:
    return round(
        stats["input_tokens"] * settings.AI_INPUT_COST_PER_MILLION / 1_000_000
        + stats["output_tokens"] * settings.AI_OUTPUT_COST_PER_MILLION / 1_000_000
        + stats["embedding_tokens"] * settings.AI_EMBEDDING_COST_PER_MILLION / 1_000_000,
        8,
    )


def execute_claimed_job(couple_id: int, worker_id: str, session_factory=SessionLocal) -> dict:
    db = session_factory()
    started = datetime.utcnow()
    run = MemorySyncRun(couple_id=couple_id, worker_id=worker_id, status="running", started_at=started)
    db.add(run)
    db.commit()
    run_id = run.id
    try:
        setting = db.query(CoupleAISettings).filter(CoupleAISettings.couple_id == couple_id).first()
        # 非聊天来源也会通过同一任务整理；include_chat 只控制聊天游标，
        # 不能让关闭聊天同步的用户同时失去日记、相册和纪念日同步。
        if not setting or not setting.enabled:
            result = {"processed_messages": 0, "created_events": 0, "merged_events": 0, "remaining_messages": 0}
            embedding = {"embedded": 0}
            usage = {"model_calls": 0, "embedding_calls": 0, "input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0}
        else:
            with ai_service.track_usage() as usage:
                result = memory_service.sync_sources(db, couple_id)
                embedding = {"embedded": result.get("embedded", 0)}

        now = datetime.utcnow()
        job = db.query(MemorySyncJob).filter(MemorySyncJob.couple_id == couple_id).with_for_update().one()
        has_new_request = bool(job.requested_at and job.last_started_at and job.requested_at > job.last_started_at)
        if result.get("remaining_messages", 0) > 0 or has_new_request:
            job.status = "pending"
            job.available_at = now
        else:
            job.status = "complete"
        job.lease_until = None
        job.leased_by = ""
        job.last_error = ""
        job.last_finished_at = now

        run.status = "success"
        run.processed_messages = result.get("processed_messages", 0)
        run.created_events = result.get("created_events", 0)
        run.merged_events = result.get("merged_events", 0)
        run.embedded_memories = embedding.get("embedded", 0)
        run.remaining_messages = result.get("remaining_messages", 0)
        for key in ("model_calls", "embedding_calls", "input_tokens", "output_tokens", "embedding_tokens"):
            setattr(run, key, usage.get(key, 0))
        run.estimated_cost_usd = _estimated_cost(usage)
        run.finished_at = now
        run.duration_ms = (now - started).total_seconds() * 1000
        db.commit()
        return {**result, **embedding, "usage": usage, "estimated_cost_usd": run.estimated_cost_usd}
    except Exception as exc:
        db.rollback()
        now = datetime.utcnow()
        job = db.query(MemorySyncJob).filter(MemorySyncJob.couple_id == couple_id).first()
        if job:
            job.status = "failed"
            job.lease_until = None
            job.leased_by = ""
            job.last_error = str(exc)[:1000]
            job.last_finished_at = now
            delay = min(300, 2 ** min(job.attempts or 1, 8))
            job.available_at = now + timedelta(seconds=delay)
        run = db.query(MemorySyncRun).filter(MemorySyncRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error = str(exc)[:1000]
            run.finished_at = now
            run.duration_ms = (now - started).total_seconds() * 1000
        db.commit()
        raise
    finally:
        db.close()


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def run_worker(stop_after_one: bool = False):
    from ..database import init_db

    init_db()
    worker_id = worker_identity()
    last_sweep = datetime.min
    while True:
        now = datetime.utcnow()
        if (now - last_sweep).total_seconds() >= 30:
            with SessionLocal() as db:
                enqueue_lagging_couples(db)
            last_sweep = now
        with SessionLocal() as db:
            couple_id = claim_next_job(db, worker_id)
        if couple_id is None:
            if stop_after_one:
                return
            time.sleep(settings.MEMORY_WORKER_POLL_SECONDS)
            continue
        try:
            execute_claimed_job(couple_id, worker_id)
        except Exception:
            pass
        if stop_after_one:
            return
