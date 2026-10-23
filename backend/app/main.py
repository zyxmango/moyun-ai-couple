"""应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import (
    auth, chat, anniversary, album, diary,
    ai_companion, ai_generate, ai_summary, rag_agent,
    settings as settings_router, admin, recipes, memory, date_planner,
)

app = FastAPI(title="情侣互动 APP API", version="1.0.0", description="情感陪伴+AI赋能")

# CORS 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件：上传的图片/头像
app.mount("/uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="uploads")

# 注册路由
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(chat.ws_router)  # WebSocket
app.include_router(anniversary.router)
app.include_router(album.router)
app.include_router(diary.router)
app.include_router(ai_companion.router)
app.include_router(ai_generate.router)
app.include_router(ai_summary.router)
app.include_router(rag_agent.router)
app.include_router(settings_router.router)
app.include_router(admin.router)
app.include_router(recipes.router)
app.include_router(memory.router)
app.include_router(date_planner.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return {"message": "情侣互动 APP API 服务运行中", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
