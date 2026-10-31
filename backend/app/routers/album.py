"""共享相册路由"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, Photo
from ..deps import get_current_user, get_active_couple
from ..services.memory_jobs import enqueue_memory_sync
from ..services.memory_service import memory_service
from ..services.object_storage import object_storage

router = APIRouter(prefix="/api/album", tags=["共享相册"])


@router.get("")
def list_photos(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    photos = db.query(Photo).filter(Photo.couple_id == couple.id).order_by(Photo.created_at.desc()).all()
    result = []
    for p in photos:
        uploader = db.query(User).filter(User.id == p.uploader_id).first()
        result.append({
            "id": p.id, "couple_id": p.couple_id, "uploader_id": p.uploader_id,
            "uploader_nickname": uploader.nickname if uploader else "",
            "filename": p.filename, "url": object_storage.url(p.file_path),
            "created_at": p.created_at.isoformat(),
        })
    return result


@router.post("")
async def upload_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    if ext.lower() not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 格式")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 50MB")
    stored_path = object_storage.put(
        f"couples/{couple.id}/album", content, file.filename, file.content_type
    )

    photo = Photo(couple_id=couple.id, uploader_id=user.id,
                  filename=file.filename, file_path=stored_path)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    enqueue_memory_sync(db, couple.id)
    db.commit()
    return {"id": photo.id, "url": object_storage.url(stored_path), "message": "上传成功"}


@router.delete("/{photo_id}")
def delete_photo(
    photo_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.couple_id == couple.id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    try:
        object_storage.delete(photo.file_path)
    except Exception:
        pass
    memory_service.deactivate_source(db, couple.id, "photo", photo.id)
    db.delete(photo)
    enqueue_memory_sync(db, couple.id)
    db.commit()
    return {"message": "已删除"}
