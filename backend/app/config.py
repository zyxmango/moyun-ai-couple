"""应用配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/couple_app.db")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_API_BASE: str = os.getenv("AI_API_BASE", "https://api.openai.com/v1")
    AI_MODEL: str = os.getenv("AI_MODEL", "gpt-4o-mini")
    AI_EMBEDDING_MODEL: str = os.getenv(
        "AI_EMBEDDING_MODEL",
        "text-embedding-v3" if "dashscope" in AI_API_BASE else "text-embedding-3-small",
    )
    ADMIN_PHONE: str = os.getenv("ADMIN_PHONE", "13800000000")

    # 邮件 SMTP（QQ邮箱）
    SMTP_EMAIL: str = os.getenv("SMTP_EMAIL", "")
    SMTP_AUTH_CODE: str = os.getenv("SMTP_AUTH_CODE", "")

    # 服务启动配置
    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    SERVER_RELOAD: bool = os.getenv("SERVER_RELOAD", "true").lower() in ("true", "1", "yes")

    # 路径
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    PHOTOS_DIR: Path = DATA_DIR / "uploads" / "photos"
    AVATARS_DIR: Path = DATA_DIR / "uploads" / "avatars"

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7

    @property
    def sqlite_url(self) -> str:
        # 确保使用绝对路径，便于跨目录运行
        db_path = self.DATA_DIR / "couple_app.db"
        return f"sqlite:///{db_path.as_posix()}"

    def ensure_dirs(self):
        for d in (self.DATA_DIR, self.UPLOAD_DIR, self.PHOTOS_DIR, self.AVATARS_DIR):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
