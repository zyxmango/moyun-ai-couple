"""共享相册路由"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, Photo
from ..deps import get_current_user, get_active_couple
from ..config import settings

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
            "filename": p.filename, "url": p.file_path,
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
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = settings.PHOTOS_DIR / filename
    content = await file.read()
    filepath.write_bytes(content)

    photo = Photo(couple_id=couple.id, uploader_id=user.id,
                  filename=file.filename, file_path=f"/uploads/photos/{filename}")
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return {"id": photo.id, "url": f"/uploads/photos/{filename}", "message": "上传成功"}


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
    # 删除文件
    try:
        fname = photo.file_path.rsplit("/", 1)[-1]
        (settings.PHOTOS_DIR / fname).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(photo)
    db.commit()
    return {"message": "已删除"}
