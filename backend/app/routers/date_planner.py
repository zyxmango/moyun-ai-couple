"""基于双人可见记忆的约会规划 Agent。"""
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_active_couple, get_current_user
from ..models import AICallLog, Couple, DatePlan, User
from ..schemas import DatePlanRequest
from ..services.ai_service import ai_service
from ..services.memory_service import memory_service

router = APIRouter(prefix="/api/ai/date-plan", tags=["AI约会规划"])


def _serialize(plan: DatePlan):
    try:
        sources = json.loads(plan.sources or "[]")
    except json.JSONDecodeError:
        sources = []
    return {
        "id": plan.id,
        "city": plan.city,
        "desired_date": plan.desired_date,
        "budget": plan.budget,
        "duration": plan.duration,
        "preferences": plan.preferences,
        "avoid": plan.avoid,
        "content": plan.content,
        "sources": sources,
        "created_at": plan.created_at.isoformat(),
    }


@router.post("")
def create_date_plan(
    data: DatePlanRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    settings = memory_service.get_settings(db, couple.id)
    if settings.enabled:
        memory_service.sync_sources(db, couple.id)
    query = " ".join(filter(None, [
        data.city, data.preferences, data.avoid,
        "约会 喜欢 偏好 计划 旅行 美食 电影",
    ]))
    sources = memory_service.search(db, couple.id, query, top_k=8, user_id=user.id) if settings.enabled else []
    request_data = data.model_dump()
    content = ai_service.date_plan(request_data, sources)
    plan = DatePlan(
        couple_id=couple.id,
        created_by=user.id,
        city=data.city.strip()[:80],
        desired_date=data.desired_date.strip()[:30],
        budget=data.budget.strip()[:50],
        duration=data.duration.strip()[:50],
        preferences=data.preferences.strip()[:1000],
        avoid=data.avoid.strip()[:1000],
        content=content,
        sources=json.dumps(sources, ensure_ascii=False),
    )
    db.add(plan)
    db.add(AICallLog(
        user_id=user.id,
        feature="date_plan",
        input_text=json.dumps(request_data, ensure_ascii=False),
        output_text=content,
        status="success",
    ))
    db.commit()
    db.refresh(plan)
    return _serialize(plan)


@router.get("")
def list_date_plans(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    # 方案可能引用创建者的私密记忆，因此历史记录也只对创建者本人可见。
    rows = db.query(DatePlan).filter(
        DatePlan.couple_id == couple.id,
        DatePlan.created_by == user.id,
    ).order_by(DatePlan.id.desc()).limit(limit).all()
    return {"items": [_serialize(item) for item in rows]}
