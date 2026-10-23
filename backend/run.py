"""后端启动入口：自动读取 .env 中的 SERVER_HOST / SERVER_PORT / SERVER_RELOAD"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.SERVER_RELOAD,
    )
