"""后台管理路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import User, Couple, Message, Diary, Photo, AICallLog, Document, Anniversary
from ..deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["后台管理"])


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
