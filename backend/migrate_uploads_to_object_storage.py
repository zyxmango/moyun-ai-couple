"""Copy legacy ``/uploads`` files to the configured S3-compatible storage.

The database is updated only after every readable source has been copied. Local
files are deliberately retained as a rollback backup. Running the script again
is safe because only references that still start with ``/uploads/`` are handled.
"""
from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Couple, Message, Photo, Recipe, User
from app.services.object_storage import object_storage


def _copy_reference(reference: str, cache: dict[str, str]) -> str | None:
    if not reference or not reference.startswith("/uploads/"):
        return None
    if reference in cache:
        return cache[reference]
    relative = reference.removeprefix("/uploads/")
    source = (settings.UPLOAD_DIR / relative).resolve()
    if not source.is_relative_to(settings.UPLOAD_DIR.resolve()) or not source.is_file():
        raise FileNotFoundError(relative)
    category = Path(relative).parent.as_posix()
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    cache[reference] = object_storage.put(category, source.read_bytes(), source.name, content_type)
    return cache[reference]


def migrate(dry_run: bool = True) -> dict[str, int]:
    if not object_storage.uses_s3:
        raise RuntimeError("STORAGE_BACKEND 必须配置为 s3")
    init_db()
    object_storage.ensure_bucket()
    cache: dict[str, str] = {}
    counters = {"migrated": 0, "missing": 0}

    with SessionLocal() as db:
        targets = []
        targets.extend((user, "avatar") for user in db.query(User).all())
        targets.extend((couple, "hero_bg") for couple in db.query(Couple).all())
        targets.extend((couple, "chat_bg") for couple in db.query(Couple).all())
        targets.extend((photo, "file_path") for photo in db.query(Photo).all())
        targets.extend((recipe, "cover") for recipe in db.query(Recipe).all())
        targets.extend(
            (message, "content")
            for message in db.query(Message).filter(Message.msg_type.in_(("image", "video"))).all()
        )

        for record, field in targets:
            current = getattr(record, field) or ""
            if not current.startswith("/uploads/"):
                continue
            if dry_run:
                relative = current.removeprefix("/uploads/")
                source = (settings.UPLOAD_DIR / relative).resolve()
                if source.is_relative_to(settings.UPLOAD_DIR.resolve()) and source.is_file():
                    counters["migrated"] += 1
                else:
                    counters["missing"] += 1
                continue
            try:
                replacement = _copy_reference(current, cache)
            except FileNotFoundError:
                counters["missing"] += 1
                continue
            if replacement:
                counters["migrated"] += 1
                if not dry_run:
                    setattr(record, field, replacement)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    return counters


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="上传文件并更新数据库引用")
    args = parser.parse_args()
    result = migrate(dry_run=not args.apply)
    print(f"migrated={result['migrated']} missing={result['missing']} dry_run={not args.apply}")
