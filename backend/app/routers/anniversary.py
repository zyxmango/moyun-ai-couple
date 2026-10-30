"""纪念日路由"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, Anniversary, Reminder
from ..schemas import AnniversaryCreate, AnniversaryUpdate, AnniversaryOut
from ..deps import get_current_user, get_active_couple
from ..services.memory_jobs import enqueue_memory_sync
from ..services.memory_service import memory_service

router = APIRouter(prefix="/api/anniversaries", tags=["纪念日"])


def _days_until(d: date) -> int:
    today = date.today()
    next_d = d.replace(year=today.year)
    if next_d < today:
        next_d = next_d.replace(year=today.year + 1)
    return (next_d - today).days


@router.get("")
def list_anniversaries(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    items = db.query(Anniversary).filter(Anniversary.couple_id == couple.id).order_by(Anniversary.date).all()
    return [{
        "id": a.id, "couple_id": a.couple_id, "title": a.title,
        "description": a.description, "date": a.date.isoformat(),
        "reminder_enabled": a.reminder_enabled, "created_at": a.created_at.isoformat(),
        "days_until": _days_until(a.date) if a.reminder_enabled else None,
    } for a in items]


@router.post("")
def create_anniversary(
    data: AnniversaryCreate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    ann = Anniversary(couple_id=couple.id, title=data.title, description=data.description,
                      date=data.date, reminder_enabled=data.reminder_enabled)
    db.add(ann)
    db.commit()
    db.refresh(ann)
    # 创建提醒
    if data.reminder_enabled:
        reminder = Reminder(couple_id=couple.id, reminder_type="anniversary",
                            content=f"纪念日「{data.title}」即将到来", trigger_date=data.date)
        db.add(reminder)
        db.commit()
    enqueue_memory_sync(db, couple.id)
    db.commit()
    return {"id": ann.id, "message": "纪念日已创建"}


@router.put("/{ann_id}")
def update_anniversary(
    ann_id: int,
    data: AnniversaryUpdate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    ann = db.query(Anniversary).filter(Anniversary.id == ann_id, Anniversary.couple_id == couple.id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="纪念日不存在")
    if data.title is not None:
        ann.title = data.title
    if data.description is not None:
        ann.description = data.description
    if data.date is not None:
        ann.date = data.date
    if data.reminder_enabled is not None:
        ann.reminder_enabled = data.reminder_enabled
    db.commit()
    enqueue_memory_sync(db, couple.id)
    db.commit()
    return {"message": "已更新"}


@router.delete("/{ann_id}")
def delete_anniversary(
    ann_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    ann = db.query(Anniversary).filter(Anniversary.id == ann_id, Anniversary.couple_id == couple.id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="纪念日不存在")
    memory_service.deactivate_source(db, couple.id, "anniversary", ann.id)
    db.delete(ann)
    enqueue_memory_sync(db, couple.id)
    db.commit()
    return {"message": "已删除"}
