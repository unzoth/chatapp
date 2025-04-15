from sqlalchemy import Column, Integer, CHAR, String, Text, DateTime, ForeignKey, Enum, CheckConstraint, BigInteger, SmallInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db import Base

class User(Base):
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(CHAR(64), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    token = Column(String(255), nullable=True)  # 用户的认证令牌
    token_expiry = Column(DateTime, nullable=True)  # 令牌过期时间
    img=Column(String(255))

    # 关联到对话，级联删除
    dialogs = relationship("Dialog", back_populates="owner", cascade="all, delete-orphan")


class Dialog(Base):
    __tablename__ = 'dialogs'

    dialog_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete="CASCADE"), nullable=False)
    title = Column(String(100), default="新对话")
    created_at = Column(DateTime, server_default=func.current_timestamp())

    # 关联到用户（对话所属者）
    owner = relationship("User", back_populates="dialogs")
    # 关联到聊天记录
    chat_records = relationship("ChatRecord", back_populates="dialog", cascade="all, delete-orphan")


class ChatRecord(Base):
    __tablename__ = 'chat_records'

    record_id = Column(BigInteger, primary_key=True, index=True)
    dialog_id = Column(Integer, ForeignKey('dialogs.dialog_id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete="CASCADE"), nullable=False)
    # 修改为允许 NULL，用于 AI 回复；对于用户消息，业务层确保 content 非空
    content = Column(Text, nullable=True)
    role = Column(SmallInteger, nullable=False)
    __table_args__ = (CheckConstraint('role IN (0, 1)', name='check_role'),)
    media_url = Column(String(255))
    media_type = Column(Enum('image', 'file', 'video', name='media_type_enum'))
    # 新增 reasoning_content 字段，用于存储 AI 回复时的 reasoning 内容（可为空）
    reasoning_content = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())

    dialog = relationship("Dialog", back_populates="chat_records")
    user = relationship("User")
