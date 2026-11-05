"""Validation shared by image and video upload endpoints."""
from fastapi import HTTPException


IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}


def validate_image_bytes(content: bytes, maximum_bytes: int) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="图片内容为空")
    if len(content) > maximum_bytes:
        raise HTTPException(status_code=400, detail=f"图片不能超过 {maximum_bytes // 1024 // 1024}MB")
    signatures = (
        content.startswith(b"\xff\xd8\xff"),
        content.startswith(b"\x89PNG\r\n\x1a\n"),
        content.startswith((b"GIF87a", b"GIF89a")),
        len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    )
    if not any(signatures):
        raise HTTPException(status_code=400, detail="文件内容不是受支持的图片格式")


def validate_video_bytes(content: bytes, maximum_bytes: int) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="视频内容为空")
    if len(content) > maximum_bytes:
        raise HTTPException(status_code=400, detail=f"视频不能超过 {maximum_bytes // 1024 // 1024}MB")
    # MP4/MOV are ISO Base Media files (ftyp box); WebM starts with EBML.
    is_iso_media = len(content) >= 12 and content[4:8] == b"ftyp"
    is_webm = content.startswith(b"\x1aE\xdf\xa3")
    if not (is_iso_media or is_webm):
        raise HTTPException(status_code=400, detail="文件内容不是受支持的视频格式")


def validate_album_media(
    content: bytes,
    filename: str | None,
    image_maximum_bytes: int = 20 * 1024 * 1024,
    video_maximum_bytes: int = 100 * 1024 * 1024,
) -> str:
    """Validate by extension and magic bytes, returning ``image`` or ``video``."""
    extension = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if extension in IMAGE_EXTENSIONS:
        validate_image_bytes(content, image_maximum_bytes)
        return "image"
    if extension in VIDEO_EXTENSIONS:
        validate_video_bytes(content, video_maximum_bytes)
        return "video"
    raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif/mp4/webm/mov 格式")
