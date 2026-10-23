"""情侣日记路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, Diary
from ..schemas import DiaryCreate, DiaryUpdate
from ..deps import get_current_user, get_active_couple

router = APIRouter(prefix="/api/diaries", tags=["情侣日记"])


def _diary_out(d: Diary, db: Session) -> dict:
    author = db.query(User).filter(User.id == d.author_id).first()
    return {
        "id": d.id, "couple_id": d.couple_id, "author_id": d.author_id,
        "author_nickname": author.nickname if author else "",
        "title": d.title, "content": d.content, "mood": d.mood,
        "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat(),
    }


@router.get("")
def list_diaries(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    items = db.query(Diary).filter(Diary.couple_id == couple.id).order_by(Diary.created_at.desc()).all()
    return [_diary_out(d, db) for d in items]


@router.post("")
def create_diary(
    data: DiaryCreate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    diary = Diary(couple_id=couple.id, author_id=user.id, title=data.title,
                  content=data.content, mood=data.mood)
    db.add(diary)
    db.commit()
    db.refresh(diary)
    return _diary_out(diary, db)


@router.get("/{diary_id}")
def get_diary(
    diary_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    diary = db.query(Diary).filter(Diary.id == diary_id, Diary.couple_id == couple.id).first()
    if not diary:
        raise HTTPException(status_code=404, detail="日记不存在")
    return _diary_out(diary, db)


@router.put("/{diary_id}")
def update_diary(
    diary_id: int,
    data: DiaryUpdate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    diary = db.query(Diary).filter(Diary.id == diary_id, Diary.couple_id == couple.id).first()
    if not diary:
        raise HTTPException(status_code=404, detail="日记不存在")
    if data.title is not None:
        diary.title = data.title
    if data.content is not None:
        diary.content = data.content
    if data.mood is not None:
        diary.mood = data.mood
    db.commit()
    db.refresh(diary)
    return _diary_out(diary, db)


@router.delete("/{diary_id}")
def delete_diary(
    diary_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    diary = db.query(Diary).filter(Diary.id == diary_id, Diary.couple_id == couple.id).first()
    if not diary:
        raise HTTPException(status_code=404, detail="日记不存在")
    db.delete(diary)
    db.commit()
    return {"message": "已删除"}
