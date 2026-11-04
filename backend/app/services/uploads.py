"""Validation shared by image upload endpoints."""
from fastapi import HTTPException


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
