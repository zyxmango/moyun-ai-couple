"""AI 情感陪伴路由"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, AIConversation, AIMessage, AICallLog
from ..schemas import CompanionChatRequest
from ..deps import get_current_user, get_active_couple
from ..services.ai_service import ai_service
from ..services.memory_service import memory_service

router = APIRouter(prefix="/api/ai/companion", tags=["AI情感陪伴"])


def _build_history(conv: AIConversation, db: Session) -> list:
    msgs = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).order_by(AIMessage.id).all()
    history = []
    for m in msgs[-20:]:  # 最近 10 轮（20 条消息）
        history.append({"role": m.role, "content": m.content})
    return history


@router.post("/chat")
def companion_chat(
    req: CompanionChatRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    # 获取或创建对话
    if req.conversation_id:
        conv = db.query(AIConversation).filter(
            AIConversation.id == req.conversation_id,
            AIConversation.user_id == user.id,
            AIConversation.conv_type == "companion",
        ).first()
    else:
        conv = AIConversation(user_id=user.id, conv_type="companion",
                              title=req.message[:20] if req.message else "情感陪伴")
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # 保存用户消息
    user_msg = AIMessage(conversation_id=conv.id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    # 调用 AI
    history = _build_history(conv, db)
    # 移除刚加的最后一条（已在 messages 中，避免重复）
    history = history[:-1]
    # 共同记忆仅作为模型内部上下文，绝不把原始检索片段返回到聊天界面。
    sync_result = memory_service.sync_sources(db, couple.id)
    memories = (
        memory_service.search(db, couple.id, req.message, top_k=5, user_id=user.id)
        if sync_result["enabled"] else []
    )
    memory_context_lines = []
    for item in memories:
        date_note = ""
        # 聊天时间只是消息发送时间，不能冒充事件发生时间；纪念日等结构化记录可以使用日期。
        if item.get("event_date") and item.get("source_type") != "chat":
            date_note = f"（日期：{item['event_date'][:10]}）"
        memory_context_lines.append(f"- {item['title']}{date_note}：{item['content']}")
    memory_context = "\n".join(memory_context_lines)
    reply = ai_service.companion_chat(req.message, history, memory_context)

    # 保存 AI 回复
    ai_msg = AIMessage(
        conversation_id=conv.id,
        role="assistant",
        content=reply,
        sources=json.dumps(memories, ensure_ascii=False),
    )
    db.add(ai_msg)
    # 日志
    log = AICallLog(user_id=user.id, feature="companion", input_text=req.message,
                    output_text=reply, status="success")
    db.add(log)
    db.commit()
    db.refresh(ai_msg)

    return {
        "conversation_id": conv.id,
        "message": {
            "id": ai_msg.id, "role": "assistant", "content": reply,
            "sources": [], "created_at": ai_msg.created_at.isoformat(),
        },
    }


@router.get("/history")
def companion_history(
    conversation_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if conversation_id:
        convs = db.query(AIConversation).filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == user.id,
            AIConversation.conv_type == "companion",
        ).all()
    else:
        convs = db.query(AIConversation).filter(
            AIConversation.user_id == user.id,
            AIConversation.conv_type == "companion",
        ).order_by(AIConversation.created_at.desc()).all()

    result = []
    for conv in convs:
        msgs = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).order_by(AIMessage.id).all()
        result.append({
            "id": conv.id, "conv_type": conv.conv_type, "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "messages": [{
                "id": m.id, "role": m.role, "content": m.content,
                "sources": json.loads(m.sources) if m.sources else [],
                "created_at": m.created_at.isoformat(),
            } for m in msgs],
        })
    return result


@router.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = db.query(AIConversation).filter(
        AIConversation.user_id == user.id,
        AIConversation.conv_type == "companion",
    ).order_by(AIConversation.created_at.desc()).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()} for c in convs]
