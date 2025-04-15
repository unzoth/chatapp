"""
主应用程序入口

初始化FastAPI应用并挂载所有路由
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from routes import auth, dialog, chat
from config import CORS_CONFIG, STATIC_FILES_DIR, STATIC_FILES_URL

# 创建FastAPI应用
app = FastAPI(title="AI聊天助手API", description="支持对话和图像的AI聊天API服务")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    **CORS_CONFIG
)

# 确保上传目录存在
os.makedirs(STATIC_FILES_DIR, exist_ok=True)

# 挂载静态文件目录
app.mount(STATIC_FILES_URL, StaticFiles(directory=STATIC_FILES_DIR), name="uploads")

# 注册路由
app.include_router(auth.router)
app.include_router(dialog.router)
app.include_router(chat.router)


# 健康检查端点
@app.get("/health")
async def health_check():
    """
    健康检查接口

    Returns:
        应用状态信息
    """
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)