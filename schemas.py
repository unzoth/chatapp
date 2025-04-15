"""
数据传输模型定义模块

包含所有Pydantic模型用于请求验证和响应格式化
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# ----------------- 对话相关请求和响应模型 -----------------

class NewDialogRequest(BaseModel):
    """创建新对话的请求模型"""
    username: str
    conversation_title: str = "新对话"

class NewDialogResponse(BaseModel):
    """创建新对话的响应模型"""
    dialog_id: int

class UpdateTitleRequest(BaseModel):
    """更新对话标题的请求模型"""
    title: str
    username: str

# ----------------- 聊天相关请求和响应模型 -----------------

class QuestionRequest(BaseModel):
    """提问请求模型"""
    username: str
    dialog_id: Optional[int] = None  # 新对话时不传；继续对话时传入已有 dialog_id
    conversation_title: str = "新对话"
    question: str
    model: str = "model1"  # 可选值："model1"、"model2"、"model3"
    image_base64: Optional[str] = None
    image_path: Optional[str] = None

class StopRequest(BaseModel):
    """停止生成回复的请求模型"""
    dialog_id: int
    username: str

# ----------------- 认证相关请求和响应模型 -----------------

class RegisterRequest(BaseModel):
    """注册请求模型"""
    username: str
    password: str

class RegisterResponse(BaseModel):
    """注册响应模型"""
    message: str
    user_id: int
    token: Optional[str] = None  # 新增，注册时可选返回令牌

class LoginRequest(BaseModel):
    """登录请求模型"""
    username: str
    password: str

class LoginResponse(BaseModel):
    """登录响应模型"""
    message: str
    user_id: int
    token: str  # 新增，登录成功时返回令牌

class TokenVerifyRequest(BaseModel):
    username: str
    token: str

class TokenVerifyResponse(BaseModel):
    valid: bool
    message: str

class DeleteDialogRequest(BaseModel):
    """删除对话请求模型"""
    username: str

# 定义修改密码请求模型
class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str

# 定义修改密码响应模型
class ChangePasswordResponse(BaseModel):
    message: str
    success: bool

# ----------------- 对话与聊天记录的响应模型 -----------------

class ChatRecordResponse(BaseModel):
    """聊天记录响应模型"""
    record_id: int
    content: str
    role: int  # 1 表示用户发送，0 表示 AI 回复
    created_at: datetime
    media_url: Optional[str] = None
    reasoning_content: Optional[str] = None

class DialogWithRecordsResponse(BaseModel):
    """带有聊天记录的对话响应模型"""
    dialog_id: int
    title: str
    chat_records: List[ChatRecordResponse]

class GetDialogsResponse(BaseModel):
    """获取对话列表的响应模型"""
    conversations: List[DialogWithRecordsResponse]