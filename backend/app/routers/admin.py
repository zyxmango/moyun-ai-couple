"""后台管理路由"""
from datetime import datetime, timedelta
import statistics
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import (
    User, Couple, Message, Diary, Photo, AICallLog, Document, Anniversary,
    CoupleAISettings, MemorySyncJob, MemorySyncRun, SharedMemory,
)
from ..deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["后台管理"])


@router.get("/memory-health")
def memory_health(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """只返回聚合运行指标，不暴露聊天正文或记忆内容。"""
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    settings_rows = db.query(CoupleAISettings).filter(CoupleAISettings.enabled.is_(True)).all()
    lags = []
    for row in settings_rows:
        newest = db.query(func.max(Message.id)).filter(Message.couple_id == row.couple_id).scalar() or 0
        lags.append(max(0, newest - (row.last_synced_message_id or 0)))
    jobs = dict(db.query(MemorySyncJob.status, func.count(MemorySyncJob.couple_id)).group_by(
        MemorySyncJob.status
    ).all())
    runs = db.query(MemorySyncRun).filter(MemorySyncRun.started_at >= since).all()
    durations = sorted(row.duration_ms or 0 for row in runs if row.status == "success")
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))] if durations else 0
    failures = sum(1 for row in runs if row.status == "failed")
    unembedded = db.query(func.count(SharedMemory.id)).filter(
        SharedMemory.status == "confirmed", SharedMemory.is_active.is_(True),
        (SharedMemory.embedding_b64 == "") | SharedMemory.embedding_b64.is_(None),
    ).scalar() or 0
    return {
        "generated_at": now.isoformat(),
        "enabled_couples": len(settings_rows),
        "message_lag_total": sum(lags),
        "message_lag_max": max(lags, default=0),
        "couples_with_sync_error": sum(1 for row in settings_rows if row.sync_error),
        "jobs": {"pending": jobs.get("pending", 0), "running": jobs.get("running", 0),
                 "failed": jobs.get("failed", 0), "complete": jobs.get("complete", 0)},
        "unembedded_memories": unembedded,
        "last_24h": {
            "runs": len(runs),
            "failures": failures,
            "failure_rate": round(failures / len(runs), 4) if runs else 0,
            "duration_median_ms": round(statistics.median(durations), 2) if durations else 0,
            "duration_p95_ms": round(p95, 2),
            "processed_messages": sum(row.processed_messages or 0 for row in runs),
            "model_calls": sum(row.model_calls or 0 for row in runs),
            "embedding_calls": sum(row.embedding_calls or 0 for row in runs),
            "input_tokens": sum(row.input_tokens or 0 for row in runs),
            "output_tokens": sum(row.output_tokens or 0 for row in runs),
            "embedding_tokens": sum(row.embedding_tokens or 0 for row in runs),
            "estimated_cost_usd": round(sum(row.estimated_cost_usd or 0 for row in runs), 6),
        },
    }


@router.get("/stats")
def stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "couples_active": db.query(func.count(Couple.id)).filter(Couple.status == "active").scalar(),
        "couples_total": db.query(func.count(Couple.id)).scalar(),
        "messages": db.query(func.count(Message.id)).scalar(),
        "diaries": db.query(func.count(Diary.id)).scalar(),
        "photos": db.query(func.count(Photo.id)).scalar(),
        "ai_calls": db.query(func.count(AICallLog.id)).scalar(),
        "documents": db.query(func.count(Document.id)).scalar(),
        "anniversaries": db.query(func.count(Anniversary.id)).scalar(),
    }


@router.get("/users")
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [{
        "id": u.id, "phone": u.phone, "nickname": u.nickname,
        "avatar": u.avatar, "couple_id": u.couple_id,
        "is_admin": u.is_admin, "notify_enabled": u.notify_enabled,
        "created_at": u.created_at.isoformat(),
    } for u in users]


@router.get("/couples")
def list_couples(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    couples = db.query(Couple).order_by(Couple.created_at.desc()).all()
    result = []
    for c in couples:
        u1 = db.query(User).filter(User.id == c.user1_id).first()
        u2 = db.query(User).filter(User.id == c.user2_id).first() if c.user2_id else None
        result.append({
            "id": c.id, "pairing_code": c.pairing_code, "status": c.status,
            "user1_phone": u1.phone if u1 else "", "user1_nickname": u1.nickname if u1 else "",
            "user2_phone": u2.phone if u2 else "", "user2_nickname": u2.nickname if u2 else "",
            "created_at": c.created_at.isoformat(),
        })
    return result


@router.get("/ai-logs")
def ai_logs(
    feature: str = "",
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(AICallLog)
    if feature:
        q = q.filter(AICallLog.feature == feature)
    logs = q.order_by(AICallLog.created_at.desc()).limit(limit).all()
    return [{
        "id": l.id, "user_id": l.user_id, "feature": l.feature,
        "input_text": l.input_text[:200] if l.input_text else "",
        "output_text": l.output_text[:200] if l.output_text else "",
        "status": l.status, "created_at": l.created_at.isoformat(),
    } for l in logs]
