"""数据库连接与会话管理"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

engine = create_engine(
    settings.sqlite_url,
    connect_args={"check_same_thread": False},  # SQLite 多线程支持
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 依赖：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建数据表，并对旧版 SQLite 做轻量、幂等的字段迁移。"""
    from . import models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "verification_codes" in inspector.get_table_names():
        code_columns = {column["name"] for column in inspector.get_columns("verification_codes")}
        if "purpose" not in code_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE verification_codes ADD COLUMN purpose VARCHAR(30) DEFAULT 'general'"))
    if "couples" in inspector.get_table_names():
        couple_columns = {column["name"] for column in inspector.get_columns("couples")}
        if "relationship_start_date" not in couple_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE couples ADD COLUMN relationship_start_date DATE"))
    if "shared_memories" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("shared_memories")}
    additions = {
        "owner_id": "INTEGER",
        "visibility": "VARCHAR(20) DEFAULT 'shared'",
        "category": "VARCHAR(30) DEFAULT 'event'",
        "version": "INTEGER DEFAULT 1",
        "is_active": "BOOLEAN DEFAULT 1",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE shared_memories ADD COLUMN {name} {definition}"))
