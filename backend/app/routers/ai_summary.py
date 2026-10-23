"""AI 日记总结路由"""
import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, Diary, AIConversation, AIMessage, AICallLog, Reminder
from ..schemas import SummaryRequest
from ..deps import get_current_user, get_active_couple
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api/ai/summary", tags=["AI日记总结"])


@router.post("/daily")
def generate_summary(
    req: SummaryRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    # 确定时间范围
    if req.date:
        end = req.date
    else:
        end = date.today()
    if req.period == "weekly":
        start = end - timedelta(days=7)
        period_label = "本周"
    else:
        start = end
        period_label = end.strftime("%Y年%m月%d日")

    # 获取日记
    diaries = db.query(Diary).filter(
        Diary.couple_id == couple.id,
        Diary.created_at >= start,
        Diary.created_at < end + timedelta(days=1),
    ).order_by(Diary.created_at).all()

    diary_texts = [f"[{d.title}] {d.content}" for d in diaries] if diaries else []
    summary = ai_service.diary_summary(diary_texts, period_label)

    # 存为 AI 对话记录
    conv = AIConversation(user_id=user.id, conv_type="generate", title=f"日记总结-{period_label}")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    msg = AIMessage(conversation_id=conv.id, role="assistant", content=summary)
    db.add(msg)
    log = AICallLog(user_id=user.id, feature="summary",
                    input_text=f"{req.period}|{period_label}", output_text=summary, status="success")
    db.add(log)
    db.commit()

    return {
        "id": conv.id, "period": req.period, "date": end.isoformat(),
        "content": summary, "diary_count": len(diaries),
        "created_at": conv.created_at.isoformat(),
    }


@router.get("/list")
def summary_list(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = db.query(AIConversation).filter(
        AIConversation.user_id == user.id,
        AIConversation.conv_type == "generate",
        AIConversation.title.like("日记总结%"),
    ).order_by(AIConversation.created_at.desc()).all()
    result = []
    for c in convs:
        msg = db.query(AIMessage).filter(AIMessage.conversation_id == c.id).first()
        result.append({
            "id": c.id, "period": "weekly" if "本周" in c.title else "daily",
            "title": c.title, "content": msg.content if msg else "",
            "created_at": c.created_at.isoformat(),
        })
    return result
