"""应用入口"""
import asyncio
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal, init_db
from .models import CoupleAISettings
from .services.memory_service import memory_service
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


def _sync_enabled_memories_once():
    db = SessionLocal()
    try:
        couple_ids = [row[0] for row in db.query(CoupleAISettings.couple_id).filter(
            CoupleAISettings.enabled.is_(True),
            CoupleAISettings.include_chat.is_(True),
        ).all()]
        for couple_id in couple_ids:
            memory_service.sync_chat_events(db, couple_id, max_batches=1)
            try:
                memory_service.ensure_embeddings(db, couple_id, limit=128)
            except Exception:
                db.rollback()
                continue
    finally:
        db.close()


async def _memory_sync_loop():
    # 延迟首轮，避免启动路径被历史数据整理阻塞；之后持续追赶游标。
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(_sync_enabled_memories_once)
        except Exception:
            # 单轮失败会保留游标，下轮从同一位置重试。
            continue


@app.on_event("startup")
async def startup():
    init_db()
    app.state.memory_sync_task = asyncio.create_task(_memory_sync_loop())


@app.on_event("shutdown")
async def shutdown():
    task = getattr(app.state, "memory_sync_task", None)
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@app.get("/")
def root():
    return {"message": "情侣互动 APP API 服务运行中", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
