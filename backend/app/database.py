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
    if "couple_ai_settings" in inspector.get_table_names():
        setting_columns = {column["name"] for column in inspector.get_columns("couple_ai_settings")}
        setting_additions = {
            "last_synced_message_id": "INTEGER DEFAULT 0 NOT NULL",
            "sync_error": "TEXT DEFAULT ''",
            "sync_updated_at": "DATETIME",
        }
        with engine.begin() as connection:
            for name, definition in setting_additions.items():
                if name not in setting_columns:
                    connection.execute(text(f"ALTER TABLE couple_ai_settings ADD COLUMN {name} {definition}"))
    if "messages" in inspector.get_table_names():
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_messages_couple_created "
                "ON messages (couple_id, created_at)"
            ))
    if "shared_memories" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("shared_memories")}
    additions = {
        "owner_id": "INTEGER",
        "visibility": "VARCHAR(20) DEFAULT 'shared'",
        "category": "VARCHAR(30) DEFAULT 'event'",
        "event_key": "VARCHAR(160) DEFAULT ''",
        "event_kind": "VARCHAR(30) DEFAULT 'event'",
        "facts": "TEXT DEFAULT '[]'",
        "version": "INTEGER DEFAULT 1",
        "is_active": "BOOLEAN DEFAULT 1",
        "memory_state": "VARCHAR(20) DEFAULT 'completed'",
        "lifecycle": "VARCHAR(20) DEFAULT 'closed'",
        "closure_reason": "VARCHAR(40) DEFAULT ''",
        "state_confidence": "FLOAT DEFAULT 1.0",
        "confidence": "FLOAT DEFAULT 1.0",
        "event_end": "DATETIME",
        "started_at": "DATETIME",
        "resolved_at": "DATETIME",
        "forgotten_at": "DATETIME",
        "valid_from": "DATETIME",
        "valid_to": "DATETIME",
        "source_message_ids": "TEXT DEFAULT '[]'",
        "embedding_b64": "TEXT DEFAULT ''",
        "embedding_model": "VARCHAR(100) DEFAULT ''",
        "embedding_dim": "INTEGER DEFAULT 0",
        "embedding_updated_at": "DATETIME",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE shared_memories ADD COLUMN {name} {definition}"))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_memory_retrieval "
            "ON shared_memories (couple_id, status, is_active)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_shared_memories_embedding_model "
            "ON shared_memories (embedding_model)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_shared_memories_event_key "
            "ON shared_memories (event_key)"
        ))
        # 旧版把每条聊天直接当作记忆；保留数据便于追溯，但停止参与检索。
        connection.execute(text("UPDATE shared_memories SET is_active = 0 WHERE source_type = 'chat'"))

    table_additions = {
        "memory_candidates": {
            "facts": "TEXT DEFAULT '[]'",
            "started_at": "DATETIME",
            "resolved_at": "DATETIME",
        },
        "memory_event_history": {"facts": "TEXT DEFAULT '[]'"},
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in table_additions.items():
            if table_name not in inspector.get_table_names():
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for name, definition in columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))
