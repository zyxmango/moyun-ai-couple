"""AI 内容生成路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, AICallLog
from ..schemas import GenerateRequest
from ..deps import get_current_user
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api/ai/generate", tags=["AI内容生成"])


@router.post("")
def generate_content(
    req: GenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = ai_service.generate_content(req.scene, req.keywords, req.extra)
    log = AICallLog(user_id=user.id, feature="generate",
                    input_text=f"{req.scene}|{req.keywords}|{req.extra}",
                    output_text=result, status="success")
    db.add(log)
    db.commit()
    return {"content": result, "scene": req.scene}
