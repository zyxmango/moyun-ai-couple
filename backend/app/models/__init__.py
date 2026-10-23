"""SQLAlchemy 数据模型"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date, ForeignKey, JSON,
    Float, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ..database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nickname = Column(String(50), default="")
    avatar = Column(String(500), default="")
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=True)
    is_admin = Column(Boolean, default=False)
    notify_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    couple = relationship("Couple", foreign_keys="User.couple_id", back_populates="members")


class Couple(Base):
    __tablename__ = "couples"
    id = Column(Integer, primary_key=True, index=True)
    pairing_code = Column(String(20), unique=True, index=True, nullable=False)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default="pending")  # pending/active/dissolved
    hero_bg = Column(String(500), default="")  # 首页 Hero 自定义背景图 URL
    chat_bg = Column(String(500), default="")  # 聊天背景（预设 key 或自定义图 URL）
    relationship_start_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("User", foreign_keys="User.couple_id", back_populates="couple")
    user1 = relationship("User", foreign_keys=[user1_id])
    user2 = relationship("User", foreign_keys=[user2_id])


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), index=True, nullable=False)
    code = Column(String(10), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    purpose = Column(String(30), default='general', nullable=False)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, default="")
    msg_type = Column(String(20), default="text")  # text/image
    read_status = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    sender = relationship("User", foreign_keys=[sender_id])


class Anniversary(Base):
    __tablename__ = "anniversaries"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, default="")
    date = Column(Date, nullable=False)
    reminder_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Photo(Base):
    __tablename__ = "photos"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    uploader = relationship("User", foreign_keys=[uploader_id])


class Diary(Base):
    __tablename__ = "diaries"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), default="")
    content = Column(Text, default="")
    mood = Column(String(20), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = relationship("User", foreign_keys=[author_id])


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conv_type = Column(String(20), nullable=False)  # companion/generate/rag
    title = Column(String(200), default="")
    context = Column(Text, default="[]")  # JSON 上下文
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("AIMessage", back_populates="conversation", order_by="AIMessage.id")


class AIMessage(Base):
    __tablename__ = "ai_messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user/assistant
    content = Column(Text, default="")
    sources = Column(Text, default="[]")  # RAG 来源 JSON
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("AIConversation", back_populates="messages")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content = Column(Text, default="")
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    chunk_index = Column(Integer, default=0)
    content = Column(Text, default="")
    vector_b64 = Column(Text, default="")  # TF-IDF 向量 Base64

    document = relationship("Document", back_populates="chunks")


class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    reminder_type = Column(String(20), default="anniversary")
    content = Column(Text, default="")
    trigger_date = Column(Date, nullable=False)
    is_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AICallLog(Base):
    __tablename__ = "ai_call_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    feature = Column(String(50), nullable=False)
    input_text = Column(Text, default="")
    output_text = Column(Text, default="")
    status = Column(String(20), default="success")
    created_at = Column(DateTime, default=datetime.utcnow)


class CoupleAISettings(Base):
    """情侣共同记忆的隐私设置，独立成表以兼容已有数据库。"""
    __tablename__ = "couple_ai_settings"
    couple_id = Column(Integer, ForeignKey("couples.id"), primary_key=True)
    enabled = Column(Boolean, default=False)
    include_chat = Column(Boolean, default=True)
    include_diary = Column(Boolean, default=True)
    include_album = Column(Boolean, default=True)
    include_anniversary = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SharedMemory(Base):
    """由情侣业务数据同步或 AI 提取出的统一共同记忆。"""
    __tablename__ = "shared_memories"
    __table_args__ = (
        UniqueConstraint("couple_id", "source_type", "source_id", name="uq_memory_source"),
    )
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    source_type = Column(String(30), nullable=False, index=True)
    source_id = Column(String(80), nullable=False)
    title = Column(String(200), default="")
    content = Column(Text, nullable=False)
    event_date = Column(DateTime, nullable=True, index=True)
    location = Column(String(100), default="")
    emotion = Column(String(30), default="")
    tags = Column(Text, default="[]")
    importance = Column(Float, default=0.5)
    status = Column(String(20), default="confirmed", index=True)  # pending/confirmed/rejected
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    visibility = Column(String(20), default="shared", index=True)  # shared/private
    category = Column(String(30), default="event", index=True)  # event/preference/plan
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DatePlan(Base):
    """基于双方可见记忆生成的约会方案。"""
    __tablename__ = "date_plans"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    city = Column(String(80), default="")
    desired_date = Column(String(30), default="")
    budget = Column(String(50), default="")
    duration = Column(String(50), default="")
    preferences = Column(Text, default="")
    avoid = Column(Text, default="")
    content = Column(Text, nullable=False)
    sources = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyQuestion(Base):
    __tablename__ = "daily_questions"
    __table_args__ = (
        UniqueConstraint("couple_id", "question_date", name="uq_daily_question_date"),
    )
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    question_date = Column(Date, nullable=False, index=True)
    question = Column(Text, nullable=False)
    category = Column(String(30), default="daily")
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyAnswer(Base):
    __tablename__ = "daily_answers"
    __table_args__ = (
        UniqueConstraint("question_id", "user_id", name="uq_daily_answer_user"),
    )
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("daily_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Recipe(Base):
    """情侣菜谱"""
    __tablename__ = "recipes"
    id = Column(Integer, primary_key=True, index=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # 创建者
    chef_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 谁做的（默认=author）
    title = Column(String(100), nullable=False)
    cover = Column(String(500), default="")
    category = Column(String(20), default="dinner")  # breakfast/lunch/dinner/dessert/snack/drink
    difficulty = Column(String(20), default="easy")  # easy/medium/hard
    cook_time = Column(Integer, default=30)  # 分钟
    ingredients = Column(Text, default="[]")  # JSON: [{name, amount}]
    steps = Column(Text, default="[]")  # JSON: ["步骤1", "步骤2"]
    cook_count = Column(Integer, default=0)  # 烹饪次数
    want_eat = Column(Boolean, default=False)  # 是否在想吃清单
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = relationship("User", foreign_keys=[author_id])
    chef = relationship("User", foreign_keys=[chef_id])
    ratings = relationship("RecipeRating", back_populates="recipe", cascade="all, delete-orphan")
    comments = relationship("RecipeComment", back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeComment.id")


class RecipeRating(Base):
    """菜谱评分（每人一次）"""
    __tablename__ = "recipe_ratings"
    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    score = Column(Integer, nullable=False)  # 1-5
    created_at = Column(DateTime, default=datetime.utcnow)

    recipe = relationship("Recipe", back_populates="ratings")
    user = relationship("User", foreign_keys=[user_id])


class RecipeComment(Base):
    """菜谱留言"""
    __tablename__ = "recipe_comments"
    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    recipe = relationship("Recipe", back_populates="comments")
    user = relationship("User", foreign_keys=[user_id])
