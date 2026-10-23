"""FastAPI 依赖注入"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Couple
from .utils import decode_access_token

security = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_access_token(creds.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的认证令牌")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def get_active_couple(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Couple:
    """获取当前用户的有效情侣关系，未绑定则 403"""
    if not user.couple_id:
        raise HTTPException(status_code=403, detail="尚未绑定情侣关系")
    couple = db.query(Couple).filter(Couple.id == user.couple_id, Couple.status == "active").first()
    if not couple:
        raise HTTPException(status_code=403, detail="情侣关系未激活或已解除")
    return couple


def get_partner(user: User, couple: Couple, db: Session) -> User | None:
    """获取情侣另一方用户"""
    partner_id = couple.user2_id if couple.user1_id == user.id else couple.user1_id
    if partner_id:
        return db.query(User).filter(User.id == partner_id).first()
    return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
