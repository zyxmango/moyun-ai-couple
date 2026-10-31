"""Move legacy /uploads files to the configured S3-compatible object store.

Dry-run by default. Run with ``--apply`` only after AIStor/S3 is reachable.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

from app.config import settings
from app.database import SessionLocal
from app.models import Couple, Message, Photo, Recipe, User
from app.services.object_storage import object_storage


@dataclass
class MigrationItem:
    record: object
    field: str
    reference: str
    category: str


def _legacy_items(db):
    for user in db.query(User).filter(User.avatar.like("/uploads/%")):
        yield MigrationItem(user, "avatar", user.avatar, f"avatars/{user.id}")
    for couple in db.query(Couple):
        for field in ("hero_bg", "chat_bg"):
            value = getattr(couple, field) or ""
            if value.startswith("/uploads/"):
                yield MigrationItem(couple, field, value, f"couples/{couple.id}/backgrounds")
    for message in db.query(Message).filter(
        Message.msg_type == "image", Message.content.like("/uploads/%")
    ):
        yield MigrationItem(message, "content", message.content, f"couples/{message.couple_id}/chat")
    for photo in db.query(Photo).filter(Photo.file_path.like("/uploads/%")):
        yield MigrationItem(photo, "file_path", photo.file_path, f"couples/{photo.couple_id}/album")
    for recipe in db.query(Recipe).filter(Recipe.cover.like("/uploads/%")):
        yield MigrationItem(recipe, "cover", recipe.cover, f"couples/{recipe.couple_id}/recipes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="upload files and update database references")
    args = parser.parse_args()

    if args.apply and not object_storage.uses_s3:
        raise SystemExit("请先设置 STORAGE_BACKEND=s3 并配置对象存储连接")

    migrated = 0
    missing = 0
    db = SessionLocal()
    try:
        items = list(_legacy_items(db))
        print(f"legacy_references={len(items)} mode={'apply' if args.apply else 'dry-run'}")
        for item in items:
            relative = item.reference.removeprefix("/uploads/")
            source = settings.UPLOAD_DIR / relative
            if not source.is_file():
                missing += 1
                print(f"missing={item.reference}")
                continue
            if not args.apply:
                continue
            stored = object_storage.put(
                item.category,
                source.read_bytes(),
                source.name,
            )
            setattr(item.record, item.field, stored)
            migrated += 1
            if migrated % 100 == 0:
                db.commit()
                print(f"migrated={migrated}")
        if args.apply:
            db.commit()
        print(f"complete migrated={migrated} missing={missing}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
