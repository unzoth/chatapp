"""
工具函数模块

包含应用程序中使用的各类辅助函数
"""
import os
import base64
import re
import hashlib
import datetime
import secrets
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import User, Dialog, ChatRecord

# ----------------- 全局停止标识 -----------------
# 用于记录每个对话的停止状态，key 为 dialog_id，value 为 bool
STOP_FLAGS = {}


def save_to_db(db: Session, user: User, dialog: Dialog, question: str, answer: str,
               image_path: Optional[str] = None):
    """
    保存聊天记录到数据库

    Args:
        db: 数据库会话
        user: 用户对象
        dialog: 对话对象
        question: 用户问题内容
        answer: AI回复内容
        image_path: 可选的图片路径

    Note:
        - 用户消息保存时，如果 image_path 存在，则存入 media_url，媒体类型设置为 "image"
        - AI 回复仅保存文本内容
    """
    chat_record_user = ChatRecord(
        dialog_id=dialog.dialog_id,
        user_id=user.user_id,
        content=question,
        role=1,
        media_url=image_path,
        media_type="image" if image_path else None
    )
    chat_record_ai = ChatRecord(
        dialog_id=dialog.dialog_id,
        user_id=user.user_id,
        content=answer,
        role=0
    )
    db.add(chat_record_user)
    db.add(chat_record_ai)
    db.commit()


def encode_image(image_path: str) -> str:
    """
    将图片编码为Base64字符串

    Args:
        image_path: 图片路径

    Returns:
        Base64编码的图片数据URI

    Raises:
        HTTPException: 当图片路径不存在时
    """
    if not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="图片路径不存在")
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def save_image_file(base64_data: str, user_id: int, dialog_id: int, original_filename: str) -> str:
    """
    保存Base64编码的图片到本地

    Args:
        base64_data: Base64编码的图片数据
        user_id: 用户ID
        dialog_id: 对话ID
        original_filename: 原始文件名

    Returns:
        保存后的相对路径
    """
    pattern = r"^data:image/.+;base64,"
    base64_str = re.sub(pattern, "", base64_data)
    directory = os.path.join("uploads", str(user_id), str(dialog_id))
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, original_filename)
    with open(file_path, "wb") as f:
        f.write(base64.b64decode(base64_str))
    relative_path = os.path.join(str(user_id), str(dialog_id), original_filename)
    return relative_path.replace("\\", "/")


def hash_password(password: str) -> str:
    """
    对密码进行哈希处理

    Args:
        password: 原始密码

    Returns:
        哈希后的密码
    """
    return hashlib.sha256(password.encode()).hexdigest()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """
    通过用户名获取用户

    Args:
        db: 数据库会话
        username: 用户名

    Returns:
        用户对象或None
    """
    return db.query(User).filter(User.username == username).first()


def generate_token() -> str:
    """生成一个随机令牌"""
    return secrets.token_hex(32)


def set_user_token(db: Session, user: User) -> str:
    """为用户设置一个新的令牌并保存到数据库"""
    token = generate_token()

    # 设置令牌过期时间（例如 30 天后）
    expiry = datetime.datetime.now() + datetime.timedelta(days=30)

    user.token = token
    user.token_expiry = expiry
    db.commit()

    return token


def verify_token(db: Session, username: str, token: str) -> bool:
    """验证用户令牌是否有效"""
    user = get_user_by_username(db, username)

    if not user or not user.token or user.token != token:
        return False

    # 检查令牌是否过期
    if user.token_expiry and user.token_expiry < datetime.datetime.now():
        return False

    return True


def invalidate_token(db: Session, username: str) -> bool:
    """使令牌失效（登出）"""
    user = get_user_by_username(db, username)

    if user:
        user.token = None
        user.token_expiry = None
        db.commit()
        return True

    return False


def get_dialog_by_id(db: Session, dialog_id: int, user_id: int) -> Optional[Dialog]:
    """
    获取特定用户的特定对话

    Args:
        db: 数据库会话
        dialog_id: 对话ID
        user_id: 用户ID

    Returns:
        对话对象或None
    """
    return db.query(Dialog).filter(Dialog.dialog_id == dialog_id, Dialog.user_id == user_id).first()


def get_chat_history(db: Session, dialog_id: int):
    """
    获取对话历史记录

    Args:
        db: 数据库会话
        dialog_id: 对话ID

    Returns:
        对话历史记录列表
    """
    return db.query(ChatRecord).filter(ChatRecord.dialog_id == dialog_id).order_by(ChatRecord.created_at).all()

