"""
配置模块

包含应用程序的全局配置设置
"""
from fastapi.middleware.cors import CORSMiddleware

# CORS 配置
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]
CORS_CONFIG = {
    "allow_origins": CORS_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

# 静态文件配置
STATIC_FILES_DIR = "uploads"
STATIC_FILES_URL = "/uploads"
STATIC_FILES_IMG = "images"
STATIC_FILES_IMG_URL = "/images"

# 系统提示信息
SYSTEM_PROMPT = "你是一位智能助手，请确保所有回复均采用 Markdown 格式输出。所有数学公式必须使用标准 LaTeX 语法输出：行内公式请使用 `$...$` 包裹；块级公式请使用 `$$...$$` 包裹。"