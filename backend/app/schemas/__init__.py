"""Pydantic 数据校验模型"""
from datetime import datetime, date
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field, field_validator


# ---------- 认证 ----------
class EmailRequest(BaseModel):
    email: str

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if len(value) > 100 or value.count('@') != 1 or any(c.isspace() for c in value):
            raise ValueError('请输入有效邮箱')
        local, domain = value.split('@')
        if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
            raise ValueError('请输入有效邮箱')
        return value


class PasswordRequest(EmailRequest):
    password: str = Field(min_length=8, max_length=72)

    @field_validator('password')
    @classmethod
    def validate_password(cls, value):
        if len(value.encode('utf-8')) > 72 or not value.strip():
            raise ValueError('密码至少 8 位，且不能超过 72 字节或全为空格')
        return value


class SendCodeRequest(EmailRequest):
    purpose: Literal['general', 'reset_password'] = 'general'

class SendCodeResponse(BaseModel):
    message: str
    code: Optional[str] = None
    delivery: str = "email"

class RegisterRequest(PasswordRequest):
    code: str
    nickname: str = ""

class LoginRequest(EmailRequest):
    password: str

class LoginCodeRequest(EmailRequest):
    code: str


class ResetPasswordRequest(PasswordRequest):
    code: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: int
    email: str
    nickname: str
    avatar: str
    couple_id: Optional[int]
    is_admin: bool
    notify_enabled: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProfileUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar: Optional[str] = None

class CoupleBindRequest(BaseModel):
    pairing_code: str


# ---------- 聊天 ----------
class MessageOut(BaseModel):
    id: int
    couple_id: int
    sender_id: int
    sender_nickname: str = ""
    content: str
    msg_type: str
    read_status: bool
    created_at: datetime
    class Config:
        from_attributes = True


# ---------- 纪念日 ----------
class AnniversaryCreate(BaseModel):
    title: str
    description: str = ""
    date: date
    reminder_enabled: bool = True

class AnniversaryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[date] = None
    reminder_enabled: Optional[bool] = None

class AnniversaryOut(BaseModel):
    id: int
    couple_id: int
    title: str
    description: str
    date: date
    reminder_enabled: bool
    created_at: datetime
    days_until: Optional[int] = None
    class Config:
        from_attributes = True


# ---------- 相册 ----------
class PhotoOut(BaseModel):
    id: int
    couple_id: int
    uploader_id: int
    uploader_nickname: str = ""
    filename: str
    url: str
    created_at: datetime
    class Config:
        from_attributes = True


# ---------- 日记 ----------
class DiaryCreate(BaseModel):
    title: str = ""
    content: str = ""
    mood: str = ""

class DiaryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    mood: Optional[str] = None

class DiaryOut(BaseModel):
    id: int
    couple_id: int
    author_id: int
    author_nickname: str = ""
    title: str
    content: str
    mood: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


# ---------- AI ----------
class CompanionChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None

class AIMessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: List[Any] = []
    created_at: datetime
    class Config:
        from_attributes = True

class AIConversationOut(BaseModel):
    id: int
    conv_type: str
    title: str
    created_at: datetime
    messages: List[AIMessageOut] = []
    class Config:
        from_attributes = True

class GenerateRequest(BaseModel):
    scene: str = "anniversary"  # anniversary/date/keyword
    keywords: str = ""
    extra: str = ""

class SummaryRequest(BaseModel):
    period: str = "daily"  # daily/weekly
    date: Optional[date] = None

class SummaryOut(BaseModel):
    id: int
    period: str
    content: str
    created_at: datetime


# ---------- RAG ----------
class RAGChatRequest(BaseModel):
    question: str
    conversation_id: Optional[int] = None

class RAGChatResponse(BaseModel):
    answer: str
    sources: List[dict] = []
    conversation_id: int

class RAGTextUploadRequest(BaseModel):
    title: str
    content: str


# ---------- AI 共同记忆 ----------
class MemorySettingsUpdate(BaseModel):
    enabled: bool
    include_chat: bool = True
    include_diary: bool = True
    include_album: bool = True
    include_anniversary: bool = True

class MemoryChatRequest(BaseModel):
    question: str
    conversation_id: Optional[int] = None

class ManualMemoryCreate(BaseModel):
    title: str
    content: str
    visibility: str = "shared"
    category: str = "preference"
    event_date: Optional[datetime] = None
    location: str = ""
    emotion: str = ""

class MemoryReviewRequest(BaseModel):
    status: str  # confirmed/rejected
    title: Optional[str] = None
    content: Optional[str] = None
    event_date: Optional[datetime] = None
    location: Optional[str] = None
    emotion: Optional[str] = None

class DailyAnswerRequest(BaseModel):
    content: str

class DatePlanRequest(BaseModel):
    city: str = ""
    desired_date: str = ""
    budget: str = ""
    duration: str = "半天"
    preferences: str = ""
    avoid: str = ""

class DocumentOut(BaseModel):
    id: int
    filename: str
    chunk_count: int
    created_at: datetime
    class Config:
        from_attributes = True


# ---------- 提醒 ----------
class ReminderOut(BaseModel):
    id: int
    reminder_type: str
    content: str
    trigger_date: date
    is_sent: bool
    class Config:
        from_attributes = True


# ---------- 菜谱 ----------
class IngredientItem(BaseModel):
    name: str
    amount: str = ""

class RecipeCreate(BaseModel):
    title: str
    cover: str = ""
    category: str = "dinner"
    difficulty: str = "easy"
    cook_time: int = 30
    chef_id: Optional[int] = None
    ingredients: List[IngredientItem] = []
    steps: List[str] = []
    want_eat: bool = False

class RecipeUpdate(BaseModel):
    title: Optional[str] = None
    cover: Optional[str] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    cook_time: Optional[int] = None
    chef_id: Optional[int] = None
    ingredients: Optional[List[IngredientItem]] = None
    steps: Optional[List[str]] = None
    want_eat: Optional[bool] = None

class RecipeCommentCreate(BaseModel):
    content: str

class RecipeCommentOut(BaseModel):
    id: int
    user_id: int
    user_nickname: str = ""
    content: str
    created_at: datetime
    class Config:
        from_attributes = True

class RecipeOut(BaseModel):
    id: int
    couple_id: int
    author_id: int
    author_nickname: str = ""
    chef_id: Optional[int] = None
    chef_nickname: str = ""
    title: str
    cover: str
    category: str
    difficulty: str
    cook_time: int
    ingredients: List[Any] = []
    steps: List[Any] = []
    cook_count: int
    want_eat: bool
    avg_score: float = 0.0
    my_score: int = 0
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


# ---------- 通用 ----------
class ApiResponse(BaseModel):
    message: str
    data: Optional[Any] = None
