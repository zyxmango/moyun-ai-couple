"""设置路由 + AI 智能提醒"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..models import User, Couple, Anniversary, Reminder
from ..schemas import ApiResponse
from ..deps import get_current_user, get_active_couple
from ..services.object_storage import object_storage

router = APIRouter(prefix="/api", tags=["设置与提醒"])


@router.put("/settings/notify", response_model=ApiResponse)
def toggle_notify(
    enabled: bool,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.notify_enabled = enabled
    db.commit()
    return ApiResponse(message=f"消息通知已{'开启' if enabled else '关闭'}")


@router.get("/ai/reminders")
def get_reminders(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """获取智能提醒：结合纪念日信息生成"""
    today = date.today()
    reminders = []

    # 数据库中的提醒
    db_reminders = db.query(Reminder).filter(
        Reminder.couple_id == couple.id,
        Reminder.trigger_date >= today,
    ).order_by(Reminder.trigger_date).all()
    for r in db_reminders:
        days = (r.trigger_date - today).days
        reminders.append({
            "id": r.id, "reminder_type": r.reminder_type,
            "content": r.content, "trigger_date": r.trigger_date.isoformat(),
            "days_until": days, "is_sent": r.is_sent,
        })

    # 动态生成纪念日提醒
    anniversaries = db.query(Anniversary).filter(
        Anniversary.couple_id == couple.id,
        Anniversary.reminder_enabled == True,
    ).all()
    for a in anniversaries:
        next_d = a.date.replace(year=today.year)
        if next_d < today:
            next_d = next_d.replace(year=today.year + 1)
        days = (next_d - today).days
        if days <= 30:  # 30 天内的纪念日提醒
            reminders.append({
                "id": f"ann_{a.id}", "reminder_type": "anniversary",
                "content": f"距离「{a.title}」还有 {days} 天"
                           + ("，是否需要准备惊喜？" if days <= 7 else ""),
                "trigger_date": next_d.isoformat(),
                "days_until": days, "is_sent": False,
            })

    reminders.sort(key=lambda x: x["days_until"])
    return reminders


@router.get("/couple/info")
def couple_info(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """获取情侣关系信息"""
    u1 = db.query(User).filter(User.id == couple.user1_id).first()
    u2 = db.query(User).filter(User.id == couple.user2_id).first() if couple.user2_id else None
    return {
        "couple_id": couple.id,
        "pairing_code": couple.pairing_code,
        "status": couple.status,
        "created_at": couple.created_at.isoformat(),
        "relationship_start_date": couple.relationship_start_date.isoformat() if couple.relationship_start_date else None,
        "hero_bg": object_storage.url(couple.hero_bg),
        "chat_bg": couple.chat_bg if (couple.chat_bg or "").startswith("preset:") else object_storage.url(couple.chat_bg),
        "user1": {"id": u1.id, "nickname": u1.nickname, "avatar": object_storage.url(u1.avatar)} if u1 else None,
        "user2": {"id": u2.id, "nickname": u2.nickname, "avatar": object_storage.url(u2.avatar)} if u2 else None,
        "is_user1": couple.user1_id == user.id,
    }


class RelationshipDateUpdate(BaseModel):
    relationship_start_date: date


@router.put("/couple/relationship-date")
def update_relationship_date(
    payload: RelationshipDateUpdate,
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    if payload.relationship_start_date > date.today():
        raise HTTPException(status_code=400, detail="恋爱开始日期不能晚于今天")
    couple.relationship_start_date = payload.relationship_start_date
    db.commit()
    return {"relationship_start_date": couple.relationship_start_date.isoformat()}


@router.post("/couple/hero-bg")
async def upload_hero_bg(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """上传首页 Hero 自定义背景图"""
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    if ext.lower() not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 格式")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 50MB")
    old_background = couple.hero_bg
    couple.hero_bg = object_storage.put(
        f"couples/{couple.id}/backgrounds", content, file.filename, file.content_type
    )
    db.commit()
    try:
        object_storage.delete(old_background)
    except Exception:
        pass
    return {"url": object_storage.url(couple.hero_bg), "message": "背景已更新"}


@router.delete("/couple/hero-bg", response_model=ApiResponse)
def reset_hero_bg(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """重置首页 Hero 背景（恢复默认渐变）"""
    old_background = couple.hero_bg
    couple.hero_bg = ""
    db.commit()
    try:
        object_storage.delete(old_background)
    except Exception:
        pass
    return ApiResponse(message="已恢复默认背景")


# ---------- 聊天背景 ----------
# 内置预设：key -> CSS 背景（前端按 key 渲染）
CHAT_BG_PRESETS = {
    "default": "",  # 默认纯色
    "cream": "linear-gradient(135deg, #faf5ec 0%, #faf0f0 100%)",
    "mint": "linear-gradient(135deg, #eef5f2 0%, #edf4f7 100%)",
    "sunset": "linear-gradient(135deg, #faf0f0 0%, #faf5ec 50%, #edf4f7 100%)",
    "lavender": "linear-gradient(135deg, #f1edf7 0%, #f5edf5 100%)",
    "ink": "linear-gradient(135deg, #f7f5f0 0%, #f1edf7 100%)",
}


@router.put("/couple/chat-bg/preset", response_model=ApiResponse)
def set_chat_bg_preset(
    key: str,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """设置聊天背景为内置预设"""
    if key not in CHAT_BG_PRESETS:
        raise HTTPException(status_code=400, detail="无效的预设")
    old_background = couple.chat_bg
    couple.chat_bg = f"preset:{key}"
    db.commit()
    if old_background and not old_background.startswith("preset:"):
        try:
            object_storage.delete(old_background)
        except Exception:
            pass
    return ApiResponse(message="聊天背景已更新")


@router.post("/couple/chat-bg")
async def upload_chat_bg(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """上传自定义聊天背景图"""
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    if ext.lower() not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 格式")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 50MB")
    old_background = couple.chat_bg
    couple.chat_bg = object_storage.put(
        f"couples/{couple.id}/backgrounds", content, file.filename, file.content_type
    )
    db.commit()
    if old_background and not old_background.startswith("preset:"):
        try:
            object_storage.delete(old_background)
        except Exception:
            pass
    return {"url": object_storage.url(couple.chat_bg), "message": "聊天背景已更新"}


@router.delete("/couple/chat-bg", response_model=ApiResponse)
def reset_chat_bg(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """恢复默认聊天背景"""
    old_background = couple.chat_bg
    couple.chat_bg = ""
    db.commit()
    if old_background and not old_background.startswith("preset:"):
        try:
            object_storage.delete(old_background)
        except Exception:
            pass
    return ApiResponse(message="已恢复默认背景")
