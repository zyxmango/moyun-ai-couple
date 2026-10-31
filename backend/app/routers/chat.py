"""聊天路由：WebSocket 实时聊天 + REST 历史记录"""
import json
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Query
from sqlalchemy import Date, cast, func, text
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models import User, Couple, Message
from ..schemas import MessageOut, ApiResponse
from ..deps import get_current_user, get_active_couple, get_partner
from ..utils import decode_access_token
from ..config import settings
from ..services.memory_jobs import enqueue_memory_sync

router = APIRouter(prefix="/api/chat", tags=["聊天"])


# ---------- WebSocket 连接管理 ----------
class ConnectionManager:
    """按 couple_id 分组管理 WebSocket 连接"""
    def __init__(self):
        # couple_id -> {user_id -> WebSocket}
        self.connections: Dict[int, Dict[int, WebSocket]] = {}

    def connect(self, couple_id: int, user_id: int, ws: WebSocket):
        if couple_id not in self.connections:
            self.connections[couple_id] = {}
        self.connections[couple_id][user_id] = ws

    def disconnect(self, couple_id: int, user_id: int):
        if couple_id in self.connections:
            self.connections[couple_id].pop(user_id, None)
            if not self.connections[couple_id]:
                del self.connections[couple_id]

    async def send_to_couple(self, couple_id: int, data: dict, exclude_user: int | None = None):
        if couple_id in self.connections:
            for uid, ws in self.connections[couple_id].items():
                if exclude_user is None or uid != exclude_user:
                    try:
                        await ws.send_json(data)
                    except Exception:
                        pass

    def is_online(self, couple_id: int, user_id: int) -> bool:
        return couple_id in self.connections and user_id in self.connections[couple_id]


manager = ConnectionManager()


def _message_timestamp(value: datetime) -> str:
    # SQLite 中的无时区消息时间按 UTC 存储；输出必须显式携带时区。
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).isoformat()


def _msg_out(msg: Message, sender: User) -> dict:
    return {
        "id": msg.id, "couple_id": msg.couple_id, "sender_id": msg.sender_id,
        "sender_nickname": sender.nickname or f"用户{sender.phone[-4:]}",
        "content": msg.content, "msg_type": msg.msg_type,
        "read_status": msg.read_status, "created_at": _message_timestamp(msg.created_at),
    }


# ---------- WebSocket 端点 ----------
ws_router = APIRouter(tags=["WebSocket聊天"])


@ws_router.websocket("/ws/chat/{token}")
async def chat_websocket(websocket: WebSocket, token: str):
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=4001)
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.couple_id:
            await websocket.close(code=4003)
            return
        couple = db.query(Couple).filter(Couple.id == user.couple_id, Couple.status == "active").first()
        if not couple:
            await websocket.close(code=4003)
            return

        await websocket.accept()
        manager.connect(couple.id, user.id, websocket)

        # 上线时推送未读消息数
        unread = db.query(Message).filter(
            Message.couple_id == couple.id,
            Message.sender_id != user.id,
            Message.read_status == False,
        ).count()
        await websocket.send_json({"type": "unread_count", "count": unread})

        # 标记对方发给我的消息为已读
        db.query(Message).filter(
            Message.couple_id == couple.id,
            Message.sender_id != user.id,
            Message.read_status == False,
        ).update({"read_status": True})
        db.commit()

        try:
            while True:
                data = await websocket.receive_text()
                payload = json.loads(data)
                content = payload.get("content", "").strip()
                msg_type = payload.get("msg_type", "text")
                if not content:
                    continue

                msg = Message(
                    couple_id=couple.id, sender_id=user.id,
                    content=content, msg_type=msg_type, read_status=False,
                )
                db.add(msg)
                db.commit()
                db.refresh(msg)
                enqueue_memory_sync(db, couple.id)
                db.commit()

                msg_data = {
                    "type": "message",
                    **_msg_out(msg, user),
                }
                # 发给自己（确认）
                await websocket.send_json(msg_data)
                # 发给对方（如果在线则标记已读）
                partner_online = manager.is_online(couple.id, msg.sender_id) is False
                # 检查对方是否在线
                partner_id = couple.user2_id if couple.user1_id == user.id else couple.user1_id
                if manager.is_online(couple.id, partner_id):
                    msg.read_status = True
                    db.commit()
                    msg_data["read_status"] = True
                await manager.send_to_couple(couple.id, msg_data, exclude_user=user.id)

        except WebSocketDisconnect:
            manager.disconnect(couple.id, user.id)
    finally:
        db.close()


# ---------- REST 接口 ----------
@router.get("/count")
def chat_count(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """返回当前情侣会话的消息总数，供前端分页状态展示。"""
    total = db.query(Message).filter(Message.couple_id == couple.id).count()
    return {"total": total}


@router.get("/calendar")
def chat_calendar(
    timezone_offset: int = Query(480, ge=-720, le=840),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """返回有聊天记录的本地日期；结果大小只与聊天天数有关。"""
    if db.get_bind().dialect.name == "postgresql":
        # PostgreSQL does not support SQLite's date(timestamp, modifier) form.
        # The offset is range-validated by FastAPI and converted to int before
        # being embedded in the interval expression.
        offset_minutes = int(timezone_offset)
        local_date = cast(
            Message.created_at + text(f"INTERVAL '{offset_minutes} minutes'"),
            Date,
        )
    else:
        local_date = func.date(Message.created_at, f"{timezone_offset:+d} minutes")
    rows = db.query(local_date.label("chat_date"), func.count(Message.id)).filter(
        Message.couple_id == couple.id,
    ).group_by(local_date).order_by(local_date.asc()).all()
    days = [{"date": chat_date, "count": count} for chat_date, count in rows if chat_date]
    return {
        "first_date": days[0]["date"] if days else None,
        "last_date": days[-1]["date"] if days else None,
        "days": days,
    }


@router.get("/history", response_model=List[dict])
def chat_history(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    before: datetime | None = Query(None),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    query = db.query(Message).filter(
        Message.couple_id == couple.id
    )
    if before is not None:
        if before.tzinfo is not None:
            before = before.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.filter(Message.created_at < before)
    msgs = query.order_by(Message.created_at.desc()).offset(offset).limit(limit).all()
    msgs.reverse()
    sender_ids = {message.sender_id for message in msgs}
    senders = {
        sender.id: sender
        for sender in db.query(User).filter(User.id.in_(sender_ids)).all()
    } if sender_ids else {}
    result = []
    for m in msgs:
        sender = senders.get(m.sender_id)
        result.append({
            "id": m.id, "couple_id": m.couple_id, "sender_id": m.sender_id,
            "sender_nickname": sender.nickname if sender else "",
            "content": m.content, "msg_type": m.msg_type,
            "read_status": m.read_status, "created_at": _message_timestamp(m.created_at),
        })
    return result


@router.put("/read/{message_id}", response_model=ApiResponse)
def mark_read(
    message_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    msg = db.query(Message).filter(Message.id == message_id, Message.couple_id == couple.id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在")
    msg.read_status = True
    db.commit()
    return ApiResponse(message="已标记已读")


@router.post("/upload")
async def upload_chat_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """上传图片，返回 URL，前端再通过 WebSocket 发送 image 类型消息"""
    import uuid
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = settings.PHOTOS_DIR / filename
    content = await file.read()
    filepath.write_bytes(content)

    msg = Message(
        couple_id=couple.id, sender_id=user.id,
        content=f"/uploads/photos/{filename}", msg_type="image", read_status=False,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    enqueue_memory_sync(db, couple.id)
    db.commit()

    msg_data = {
        "type": "message",
        "id": msg.id, "couple_id": msg.couple_id, "sender_id": msg.sender_id,
        "sender_nickname": user.nickname,
        "content": msg.content, "msg_type": "image",
        "read_status": msg.read_status, "created_at": _message_timestamp(msg.created_at),
    }
    await manager.send_to_couple(couple.id, msg_data)

    return {"url": f"/uploads/photos/{filename}", "message": msg_data}


@router.get("/unread-count")
def unread_count(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    count = db.query(Message).filter(
        Message.couple_id == couple.id,
        Message.sender_id != user.id,
        Message.read_status == False,
    ).count()
    return {"count": count}
