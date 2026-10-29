"""AI 情侣共同记忆 API。"""
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_active_couple, get_current_user
from ..models import (
    AICallLog,
    AIConversation,
    AIMessage,
    Couple,
    DailyAnswer,
    DailyQuestion,
    Message,
    MemoryEmbeddingBucket,
    SharedMemory,
    User,
)
from ..schemas import (
    DailyAnswerRequest,
    ManualMemoryCreate,
    MemoryChatRequest,
    MemoryReviewRequest,
    MemorySettingsUpdate,
)
from ..services.ai_service import ai_service
from ..services.memory_service import DEFAULT_QUESTIONS, memory_service

router = APIRouter(prefix="/api/ai/memory", tags=["AI共同记忆"])


def _settings_out(settings):
    return {
        "enabled": settings.enabled,
        "include_chat": settings.include_chat,
        "include_diary": settings.include_diary,
        "include_album": settings.include_album,
        "include_anniversary": settings.include_anniversary,
        "last_synced_message_id": settings.last_synced_message_id or 0,
        "sync_error": settings.sync_error or "",
        "sync_updated_at": settings.sync_updated_at.isoformat() if settings.sync_updated_at else None,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


@router.get("/settings")
def get_memory_settings(
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    return _settings_out(memory_service.get_settings(db, couple.id))


@router.put("/settings")
def update_memory_settings(
    data: MemorySettingsUpdate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    settings = memory_service.get_settings(db, couple.id)
    for key, value in data.model_dump().items():
        setattr(settings, key, value)
    settings.updated_at = datetime.utcnow()
    db.commit()
    if settings.enabled:
        memory_service.sync_sources(db, couple.id)
    return _settings_out(settings)


@router.post("/sync")
def sync_memories(
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    result = memory_service.sync_sources(db, couple.id)
    if not result["enabled"]:
        raise HTTPException(status_code=409, detail="请先开启 AI 共同记忆")
    return result


@router.get("")
def list_memories(
    status: str = Query("confirmed", pattern="^(confirmed|uncertain|pending|rejected|all)$"),
    source_type: str | None = None,
    visibility: str | None = Query(None, pattern="^(shared|private)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    query = db.query(SharedMemory).filter(
        SharedMemory.couple_id == couple.id,
        SharedMemory.is_active.is_(True),
        or_(
            SharedMemory.visibility == "shared",
            SharedMemory.visibility.is_(None),
            SharedMemory.owner_id == user.id,
        ),
    )
    if status != "all":
        query = query.filter(SharedMemory.status == status)
    if source_type:
        query = query.filter(SharedMemory.source_type == source_type)
    if visibility == "private":
        query = query.filter(SharedMemory.visibility == "private", SharedMemory.owner_id == user.id)
    elif visibility == "shared":
        query = query.filter(or_(SharedMemory.visibility == "shared", SharedMemory.visibility.is_(None)))
    total = query.count()
    rows = query.order_by(SharedMemory.event_date.desc(), SharedMemory.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [memory_service.serialize(row) for row in rows]}


@router.get("/{memory_id}/evidence")
def get_memory_evidence(
    memory_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    memory = db.query(SharedMemory).filter(
        SharedMemory.id == memory_id,
        SharedMemory.couple_id == couple.id,
        SharedMemory.is_active.is_(True),
    ).first()
    if not memory or (memory.visibility == "private" and memory.owner_id != user.id):
        raise HTTPException(status_code=404, detail="记忆不存在")
    source_ids = memory_service._json_ids(memory.source_message_ids)
    messages = db.query(Message).filter(
        Message.couple_id == couple.id,
        Message.id.in_(source_ids),
    ).order_by(Message.created_at.asc(), Message.id.asc()).all() if source_ids else []
    user_ids = {item.sender_id for item in messages}
    names = {
        item.id: (item.nickname or f"用户{item.id}")
        for item in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    return {
        "memory_id": memory.id,
        "items": [{
            "message_id": item.id,
            "sender_id": item.sender_id,
            "sender_nickname": names.get(item.sender_id, f"用户{item.sender_id}"),
            "content": item.content,
            "created_at": item.created_at.isoformat(),
        } for item in messages],
    }


@router.post("/manual")
def create_manual_memory(
    data: ManualMemoryCreate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    if not data.title.strip() or not data.content.strip():
        raise HTTPException(status_code=400, detail="标题和内容不能为空")
    try:
        memory = memory_service.create_manual(
            db, couple.id, user.id, data.title, data.content,
            data.visibility, data.category, data.event_date, data.location, data.emotion,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return memory_service.serialize(memory)


@router.post("/extract")
def extract_memory_candidates(
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    result = memory_service.sync_sources(db, couple.id)
    return {
        "created": result.get("created_events", 0),
        "merged": result.get("merged_events", 0),
        "processed_messages": result.get("processed_messages", 0),
        "remaining_messages": result.get("remaining_messages", 0),
        "items": [],
    }


@router.patch("/{memory_id}")
def review_memory(
    memory_id: int,
    data: MemoryReviewRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    if data.status not in {"confirmed", "rejected"}:
        raise HTTPException(status_code=400, detail="状态只能是 confirmed 或 rejected")
    memory = db.query(SharedMemory).filter(
        SharedMemory.id == memory_id,
        SharedMemory.couple_id == couple.id,
    ).first()
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    if memory.visibility == "private" and memory.owner_id != user.id:
        raise HTTPException(status_code=404, detail="记忆不存在")
    values = data.model_dump(exclude_unset=True)
    previous_text = memory_service._memory_text(memory)
    for key, value in values.items():
        setattr(memory, key, value)
    if memory_service._memory_text(memory) != previous_text or "status" in values:
        memory.embedding_b64 = ""
        memory.embedding_model = ""
        memory.embedding_dim = 0
        memory.embedding_updated_at = None
        db.query(MemoryEmbeddingBucket).filter(MemoryEmbeddingBucket.memory_id == memory.id).delete(
            synchronize_session=False
        )
    memory.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(memory)
    return memory_service.serialize(memory)


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    memory = db.query(SharedMemory).filter(
        SharedMemory.id == memory_id,
        SharedMemory.couple_id == couple.id,
    ).first()
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    if memory.visibility == "private" and memory.owner_id != user.id:
        raise HTTPException(status_code=404, detail="记忆不存在")
    db.query(MemoryEmbeddingBucket).filter(MemoryEmbeddingBucket.memory_id == memory.id).delete(
        synchronize_session=False
    )
    memory.is_active = False
    memory.status = "rejected"
    memory.forgotten_at = datetime.utcnow()
    memory.embedding_b64 = ""
    memory.embedding_model = ""
    memory.embedding_dim = 0
    memory.embedding_updated_at = None
    memory.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "这条记忆已忘记，原始聊天仍保留"}


@router.delete("")
def clear_memories(
    confirm: bool = False,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    if not confirm:
        raise HTTPException(status_code=400, detail="需要明确确认删除全部 AI 记忆")
    memory_ids = [row[0] for row in db.query(SharedMemory.id).filter(
        SharedMemory.couple_id == couple.id,
        SharedMemory.forgotten_at.is_(None),
        or_(
            SharedMemory.visibility == "shared",
            SharedMemory.visibility.is_(None),
            SharedMemory.owner_id == user.id,
        ),
    ).all()]
    if memory_ids:
        db.query(MemoryEmbeddingBucket).filter(MemoryEmbeddingBucket.memory_id.in_(memory_ids)).delete(
            synchronize_session=False
        )
    count = db.query(SharedMemory).filter(SharedMemory.id.in_(memory_ids)).delete(synchronize_session=False) if memory_ids else 0
    settings = memory_service.get_settings(db, couple.id)
    # 清空的是派生索引；游标归零后可从仍然存在的原始聊天完整重建。
    settings.last_synced_message_id = 0
    settings.sync_error = ""
    db.commit()
    return {"message": "AI 共同记忆已清空", "deleted": count}


@router.post("/chat")
def memory_chat(
    data: MemoryChatRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    if not data.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    result = memory_service.sync_sources(db, couple.id)
    if not result["enabled"]:
        raise HTTPException(status_code=409, detail="请先开启 AI 共同记忆")
    sources = memory_service.search(db, couple.id, data.question.strip(), top_k=5, user_id=user.id)
    context_parts = []
    for item in sources:
        facts = "；".join(
            f"{fact.get('type', 'fact')}"
            + (f"@{fact.get('subject_user_id')}" if fact.get('subject_user_id') is not None else "")
            + f"={fact.get('value', '')}"
            for fact in item.get("facts", []) if fact.get("value")
        )
        evidence = "；".join(
            f"{row['created_at']}：{row['content']}" for row in item.get("evidence", [])[:6]
        )
        context_parts.append(
            f"- 事件时间：{item.get('started_at') or item['event_date'] or '未知'}"
            + (f" 至 {item.get('resolved_at')}" if item.get("resolved_at") else "（尚未记录结束时间）")
            + f"；状态：{item.get('memory_state') or '未知'}；"
            f"类型：{item['title']}；内容：{item['content']}"
            + (f"；已确认事实：{facts}" if facts else "")
            + (f"；原始证据：{evidence}" if evidence else "")
        )
    context = "\n".join(context_parts) or "没有找到相关共同记忆。"

    conversation = None
    if data.conversation_id:
        conversation = db.query(AIConversation).filter(
            AIConversation.id == data.conversation_id,
            AIConversation.user_id == user.id,
            AIConversation.conv_type == "memory",
        ).first()
    if not conversation:
        conversation = AIConversation(user_id=user.id, conv_type="memory", title=data.question[:30])
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    prior = db.query(AIMessage).filter(AIMessage.conversation_id == conversation.id).order_by(AIMessage.id.desc()).limit(8).all()
    history = [{"role": item.role, "content": item.content} for item in reversed(prior)]
    answer = ai_service.memory_answer(data.question, context, history, viewer_user_id=user.id)
    db.add(AIMessage(conversation_id=conversation.id, role="user", content=data.question))
    db.add(AIMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        sources=json.dumps(sources, ensure_ascii=False),
    ))
    db.add(AICallLog(
        user_id=user.id,
        feature="memory_rag",
        input_text=data.question,
        output_text=answer,
        status="success",
    ))
    db.commit()
    return {
        "answer": answer,
        "conversation_id": conversation.id,
        "grounded": bool(sources),
    }


@router.post("/report")
def generate_memory_report(
    days: int = Query(7, ge=1, le=365),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    result = memory_service.sync_sources(db, couple.id)
    if not result["enabled"]:
        raise HTTPException(status_code=409, detail="请先开启 AI 共同记忆")
    start = datetime.utcnow() - timedelta(days=days)
    rows = db.query(SharedMemory).filter(
        SharedMemory.couple_id == couple.id,
        SharedMemory.status == "confirmed",
        SharedMemory.is_active.is_(True),
        or_(
            SharedMemory.visibility == "shared",
            SharedMemory.visibility.is_(None),
            SharedMemory.owner_id == user.id,
        ),
        or_(SharedMemory.event_date >= start, SharedMemory.created_at >= start),
    ).order_by(SharedMemory.event_date).limit(300).all()
    memories = [memory_service.serialize(row) for row in rows]
    label = "本周" if days == 7 else f"近{days}天"
    report = ai_service.memory_report(memories, label)
    conversation = AIConversation(user_id=user.id, conv_type="memory_report", title=f"共同记忆报告-{label}")
    db.add(conversation)
    db.flush()
    db.add(AIMessage(conversation_id=conversation.id, role="assistant", content=report))
    db.add(AICallLog(user_id=user.id, feature="memory_report", input_text=label, output_text=report))
    db.commit()
    return {"id": conversation.id, "period": label, "content": report, "memory_count": len(memories)}


def _daily_question_payload(db: Session, couple: Couple, user: User):
    today = date.today()
    question = db.query(DailyQuestion).filter(
        DailyQuestion.couple_id == couple.id,
        DailyQuestion.question_date == today,
    ).first()
    if not question:
        text = DEFAULT_QUESTIONS[(today.toordinal() + couple.id) % len(DEFAULT_QUESTIONS)]
        question = DailyQuestion(couple_id=couple.id, question_date=today, question=text)
        db.add(question)
        db.commit()
        db.refresh(question)
    answers = db.query(DailyAnswer).filter(DailyAnswer.question_id == question.id).all()
    mine = next((item for item in answers if item.user_id == user.id), None)
    both_answered = len({item.user_id for item in answers}) >= 2
    return {
        "id": question.id,
        "date": question.question_date.isoformat(),
        "question": question.question,
        "answered": mine is not None,
        "my_answer": mine.content if mine else "",
        "both_answered": both_answered,
        "answers": [
            {"user_id": item.user_id, "content": item.content, "created_at": item.created_at.isoformat()}
            for item in answers
        ] if both_answered else [],
    }


@router.get("/daily-question/today")
def today_question(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    return _daily_question_payload(db, couple, user)


@router.post("/daily-question/{question_id}/answer")
def answer_daily_question(
    question_id: int,
    data: DailyAnswerRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="回答不能为空")
    question = db.query(DailyQuestion).filter(
        DailyQuestion.id == question_id,
        DailyQuestion.couple_id == couple.id,
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="每日问题不存在")
    answer = db.query(DailyAnswer).filter(
        DailyAnswer.question_id == question.id,
        DailyAnswer.user_id == user.id,
    ).first()
    if answer:
        answer.content = content
    else:
        db.add(DailyAnswer(question_id=question.id, user_id=user.id, content=content))
    db.commit()
    return _daily_question_payload(db, couple, user)
