"""
对话管理路由模块

处理对话的创建、获取、更新和删除
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from db import get_db
from models import Dialog, ChatRecord
from schemas import (
    NewDialogRequest, NewDialogResponse, DeleteDialogRequest,
    UpdateTitleRequest, GetDialogsResponse
)
from utils import get_user_by_username, get_dialog_by_id

router = APIRouter(tags=["对话管理"])


@router.post("/new_dialog", response_model=NewDialogResponse)
async def create_new_dialog(request: NewDialogRequest, db: Session = Depends(get_db)):
    """
    创建新对话

    Args:
        request: 创建新对话请求
        db: 数据库会话

    Returns:
        新创建的对话ID

    Raises:
        HTTPException: 当用户不存在时
    """
    user = get_user_by_username(db, request.username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    dialog = Dialog(user_id=user.user_id, title=request.conversation_title)
    db.add(dialog)
    db.commit()
    db.refresh(dialog)

    print(f"[DEBUG] 创建新对话，dialog_id: {dialog.dialog_id}")
    return NewDialogResponse(dialog_id=dialog.dialog_id)


@router.delete("/dialog/{dialog_id}")
async def delete_dialog(dialog_id: int, username: str, db: Session = Depends(get_db)):
    """
    删除对话

    Args:
        dialog_id: 要删除的对话ID
        username: 用户名
        db: 数据库会话

    Returns:
        删除结果

    Raises:
        HTTPException: 当用户或对话不存在时
    """
    print(f"[DEBUG] 收到删除请求，dialog_id: {dialog_id}，username: {username}")
    user = get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    dialog = get_dialog_by_id(db, dialog_id, user.user_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 删除关联的聊天记录
    db.query(ChatRecord).filter(ChatRecord.dialog_id == dialog_id).delete(synchronize_session=False)
    # 删除对话
    db.delete(dialog)
    db.commit()

    return {"message": "删除成功", "dialog_id": dialog_id}


@router.put("/dialog/{dialog_id}")
async def update_dialog_title(dialog_id: int, request: UpdateTitleRequest, db: Session = Depends(get_db)):
    """
    更新对话标题

    Args:
        dialog_id: 要更新的对话ID
        request: 更新标题请求
        db: 数据库会话

    Returns:
        更新结果

    Raises:
        HTTPException: 当用户或对话不存在时
    """
    user = get_user_by_username(db, request.username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    dialog = get_dialog_by_id(db, dialog_id, user.user_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="对话不存在")

    dialog.title = request.title
    db.commit()

    return {"message": "标题更新成功", "dialog_id": dialog.dialog_id, "title": dialog.title}


@router.get("/dialogs", response_model=GetDialogsResponse)
async def get_dialogs(username: str, db: Session = Depends(get_db)):
    """
    获取用户的所有对话及其聊天记录

    Args:
        username: 用户名
        db: 数据库会话

    Returns:
        对话列表及聊天记录

    Raises:
        HTTPException: 当用户不存在时
    """
    user = get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 获取所有对话，按最后一条用户消息时间排序
    dialog_data = (
        db.query(Dialog, func.max(ChatRecord.created_at).label("last_user_message"))
        .outerjoin(ChatRecord, (ChatRecord.dialog_id == Dialog.dialog_id) & (ChatRecord.role == 1))
        .filter(Dialog.user_id == user.user_id)
        .group_by(Dialog.dialog_id)
        .order_by(desc(func.max(ChatRecord.created_at)))
        .all()
    )

    conversations = []
    for dialog, _ in dialog_data:
        # 获取每个对话的所有聊天记录
        records = (
            db.query(ChatRecord)
            .filter(ChatRecord.dialog_id == dialog.dialog_id)
            .order_by(ChatRecord.created_at)
            .all()
        )

        conv = {
            "dialog_id": dialog.dialog_id,
            "title": dialog.title,
            "chat_records": [
                {
                    "record_id": record.record_id,
                    "content": record.content,
                    "role": record.role,
                    "created_at": record.created_at,
                    "media_url": record.media_url,
                    "reasoning_content": record.reasoning_content  # 添加推理内容
                }
                for record in records
            ]
        }
        conversations.append(conv)

    return {"conversations": conversations}