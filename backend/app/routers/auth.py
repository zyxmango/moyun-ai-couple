"""认证路由：注册/登录/验证码/情侣绑定"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import User, Couple, VerificationCode
from ..schemas import (
    SendCodeRequest, SendCodeResponse, RegisterRequest, LoginRequest,
    LoginCodeRequest, ResetPasswordRequest, TokenResponse, UserOut, ProfileUpdate, CoupleBindRequest, ApiResponse,
)
from ..utils import hash_password, verify_password, create_access_token
from ..deps import get_current_user
from ..config import settings
from ..services.email_service import send_verification_email
from ..services.object_storage import object_storage

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _email_matches(column, email):
    return func.lower(func.trim(column)) == email


def _user_out(user: User) -> dict:
    return {
        "id": user.id, "email": user.email.strip().lower(), "nickname": user.nickname or "",
        "avatar": object_storage.url(user.avatar), "couple_id": user.couple_id,
        "is_admin": user.is_admin, "notify_enabled": user.notify_enabled,
        "created_at": user.created_at,
    }


@router.post("/send-code", response_model=SendCodeResponse)
def send_code(req: SendCodeRequest, db: Session = Depends(get_db)):
    """发送验证码到邮箱"""
    code = str(secrets.randbelow(900000) + 100000)
    expires = datetime.utcnow() + timedelta(minutes=5)
    vc = VerificationCode(email=req.email, code=code, expires_at=expires, purpose=req.purpose)

    # 本地开发允许不配置 SMTP：验证码随响应返回，便于迁移后直接运行。
    # 一旦在 .env 中同时配置邮箱和授权码，就自动切换为真实邮件发送，
    # 且响应不再包含验证码。
    if not settings.SMTP_EMAIL or not settings.SMTP_AUTH_CODE:
        db.add(vc)
        db.commit()
        return SendCodeResponse(
            message="SMTP 未配置，已使用本地测试验证码",
            code=code,
            delivery="local",
        )

    try:
        send_verification_email(req.email, code)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    db.add(vc)
    db.commit()
    return SendCodeResponse(message="验证码已发送到邮箱", delivery="email")


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    # 校验验证码
    vc = db.query(VerificationCode).filter(
        _email_matches(VerificationCode.email, req.email),
        VerificationCode.purpose == 'general',
        VerificationCode.code == req.code,
        VerificationCode.used == False,
        VerificationCode.expires_at > datetime.utcnow(),
    ).order_by(VerificationCode.id.desc()).first()
    if not vc:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")
    vc.used = True

    if db.query(User).filter(_email_matches(User.email, req.email)).first():
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=req.nickname or f"用户{req.email.split('@')[0][:8]}",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(_email_matches(User.email, req.email)).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.post("/login-code", response_model=TokenResponse)
def login_by_code(req: LoginCodeRequest, db: Session = Depends(get_db)):
    """邮箱 + 验证码登录"""
    vc = db.query(VerificationCode).filter(
        _email_matches(VerificationCode.email, req.email),
        VerificationCode.purpose == 'general',
        VerificationCode.code == req.code,
        VerificationCode.used == False,
        VerificationCode.expires_at > datetime.utcnow(),
    ).order_by(VerificationCode.id.desc()).first()
    if not vc:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")
    vc.used = True

    user = db.query(User).filter(_email_matches(User.email, req.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="该邮箱未注册")
    db.commit()
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.post("/reset-password", response_model=ApiResponse)
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    vc = db.query(VerificationCode).filter(
        _email_matches(VerificationCode.email, req.email),
        VerificationCode.code == req.code,
        VerificationCode.purpose == 'reset_password',
        VerificationCode.used == False,
        VerificationCode.expires_at > datetime.utcnow(),
    ).order_by(VerificationCode.id.desc()).first()
    if not vc:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")
    user = db.query(User).filter(_email_matches(User.email, req.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="该邮箱未注册")
    user.password_hash = hash_password(req.password)
    db.query(VerificationCode).filter(
        _email_matches(VerificationCode.email, req.email),
        VerificationCode.purpose == 'reset_password',
        VerificationCode.used == False,
    ).update({"used": True}, synchronize_session=False)
    db.commit()
    return ApiResponse(message="密码已重置，请使用新密码登录")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.put("/profile", response_model=UserOut)
def update_profile(
    data: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.nickname is not None:
        user.nickname = data.nickname
    if data.avatar is not None:
        user.avatar = data.avatar
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传头像"""
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    if ext.lower() not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 格式")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 50MB")
    old_avatar = user.avatar
    user.avatar = object_storage.put(
        f"avatars/{user.id}", content, file.filename, file.content_type
    )
    db.commit()
    try:
        object_storage.delete(old_avatar)
    except Exception:
        pass
    return {"url": object_storage.url(user.avatar), "message": "头像已更新"}


@router.post("/couple/generate")
def generate_pairing_code(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成配对码"""
    if user.couple_id:
        couple = db.query(Couple).filter(Couple.id == user.couple_id).first()
        if couple and couple.status == "active":
            raise HTTPException(status_code=400, detail="已绑定情侣关系")
    code = str(secrets.randbelow(900000) + 100000)
    couple = Couple(pairing_code=code, user1_id=user.id, status="pending")
    db.add(couple)
    db.commit()
    db.refresh(couple)
    user.couple_id = couple.id
    db.commit()
    return {"pairing_code": code, "couple_id": couple.id}


@router.post("/couple/bind")
def bind_couple(
    req: CoupleBindRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """通过配对码绑定情侣"""
    if user.couple_id:
        couple = db.query(Couple).filter(Couple.id == user.couple_id).first()
        if couple and couple.status == "active":
            raise HTTPException(status_code=400, detail="已绑定情侣关系")

    couple = db.query(Couple).filter(
        Couple.pairing_code == req.pairing_code,
        Couple.status == "pending",
    ).first()
    if not couple:
        raise HTTPException(status_code=400, detail="配对码无效或已被使用")
    if couple.user1_id == user.id:
        raise HTTPException(status_code=400, detail="不能与自己配对")

    couple.user2_id = user.id
    couple.status = "active"
    user.couple_id = couple.id
    db.commit()
    return {"message": "配对成功", "couple_id": couple.id}


@router.post("/couple/dissolve")
def dissolve_couple(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解除情侣关系（数据保留但无法再互动）"""
    if not user.couple_id:
        raise HTTPException(status_code=400, detail="未绑定情侣关系")
    couple = db.query(Couple).filter(Couple.id == user.couple_id).first()
    if not couple:
        raise HTTPException(status_code=404, detail="情侣关系不存在")
    couple.status = "dissolved"
    db.commit()
    return {"message": "情侣关系已解除，数据已保留"}


@router.post("/logout", response_model=ApiResponse)
def logout():
    """退出登录（JWT 无状态，前端清除令牌即可）"""
    return ApiResponse(message="已退出登录")
