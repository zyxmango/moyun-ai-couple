"""应用入口"""
import asyncio
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal, init_db
from .services.memory_jobs import enqueue_lagging_couples, claim_next_job, execute_claimed_job, worker_identity
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


def _sync_enabled_memories_once(worker_id: str):
    db = SessionLocal()
    couple_id = None
    try:
        enqueue_lagging_couples(db)
        couple_id = claim_next_job(db, worker_id)
    finally:
        db.close()
    if couple_id is not None:
        execute_claimed_job(couple_id, worker_id)


async def _memory_sync_loop():
    worker_id = worker_identity()
    while True:
        await asyncio.sleep(settings.MEMORY_WORKER_POLL_SECONDS)
        try:
            await asyncio.to_thread(_sync_enabled_memories_once, worker_id)
        except Exception:
            # 单轮失败会保留游标，下轮从同一位置重试。
            continue


@app.on_event("startup")
async def startup():
    init_db()
    app.state.memory_sync_task = (
        asyncio.create_task(_memory_sync_loop()) if settings.MEMORY_WORKER_IN_PROCESS else None
    )


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
